"""MediAid web API (FastAPI). The React app in frontend/ talks to these endpoints.

Run:  python -m uvicorn app.api:app --reload --port 8000
"""
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import VERSION, config
from app.checkin import FEELINGS, CheckinGame
from app.db import DB
from app.doctors import find_doctors
from app.intake import IntakeSession
from app.rag import RemedyRAG
from app.triage import LEVEL_MEANING, triage

app = FastAPI(title="MediAid API", version=VERSION)
print(f"MediAid version {VERSION} starting")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

# Vercel's filesystem is read-only except /tmp, so the database lives there when deployed.
_DEFAULT_DB = "/tmp/mediaid.db" if os.getenv("VERCEL") else "mediaid.db"
db = DB(os.getenv("MEDIAID_DB", _DEFAULT_DB))
_state: dict = {"llm": None, "fast": None, "rag": None}
sessions: dict[str, dict] = {}  # symptom chats in progress (kept in memory)

GREETING = {
    "en": "Hello! I'm MediAid. Tell me what's bothering you, in English, Hindi or Marathi.",
}


def get_llm():
    if _state["llm"] is None:
        from app.llm import GroqLLM
        try:
            _state["llm"] = GroqLLM()
        except RuntimeError as e:
            raise HTTPException(503, str(e))
    return _state["llm"]


def get_fast_llm():
    """Smaller, faster model for chat questions and home care."""
    if _state["fast"] is None:
        if config.GROQ_FAST_MODEL and config.GROQ_FAST_MODEL != config.GROQ_MODEL:
            from app.llm import GroqLLM
            try:
                _state["fast"] = GroqLLM(model=config.GROQ_FAST_MODEL)
            except RuntimeError as e:
                raise HTTPException(503, str(e))
        else:
            _state["fast"] = get_llm()
    return _state["fast"]


def get_rag():
    if _state["rag"] is None:
        _state["rag"] = RemedyRAG(get_fast_llm())
    return _state["rag"]


def llm_call(fn, *args, **kwargs):
    """Turn Groq errors into a readable message for the screen."""
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "model_not_found" in msg or "does not exist" in msg:
            msg = (f"Groq can't find one of the models ('{config.GROQ_MODEL}' or '{config.GROQ_FAST_MODEL}'). "
                   "Check GROQ_MODEL and GROQ_FAST_MODEL in .env.")
        elif "401" in msg or "invalid_api_key" in msg.lower():
            msg = "Groq rejected the API key. Check GROQ_API_KEY in .env."
        elif "429" in msg:
            msg = "Groq rate limit reached. Wait a minute and try again."
        raise HTTPException(502, msg)


# ---------------------------------------------------------------------------
class Message(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CheckinIn(BaseModel):
    feeling: str
    score: int = Field(ge=1, le=10)
    quests_done: list[str] = []
    note: str = ""


@app.get("/api/health")
def health():
    return {"version": VERSION, "groq_key": bool(config.GROQ_API_KEY), "model": config.GROQ_MODEL,
            "google_places": bool(config.GOOGLE_PLACES_API_KEY), "geoapify": bool(config.GEOAPIFY_API_KEY)}


@app.post("/api/symptoms/start")
def start_symptoms():
    sid = uuid.uuid4().hex
    sessions[sid] = {"intake": IntakeSession(get_fast_llm()), "first": None}
    return {"session_id": sid, "greeting": GREETING["en"]}


@app.post("/api/symptoms/{sid}/message")
def symptom_message(sid: str, body: Message):
    s = sessions.get(sid)
    if s is None:
        raise HTTPException(404, "This chat has expired. Start a new symptom check.")
    s["first"] = s["first"] or body.text
    step = llm_call(s["intake"].step, body.text)
    if not step["done"]:
        return {"done": False, "question": step["question"], "language": step["language"]}

    intake = s["intake"]
    t = llm_call(triage, get_llm(), text=s["first"], profile=intake.profile, language=intake.language)
    if not t["valid"]:
        t["level"], t["meaning"] = "yellow", LEVEL_MEANING["yellow"]
    remedies = get_rag().get_remedies(text=s["first"], profile=intake.profile, triage=t,
                                      language=intake.language)
    result = {
        "level": t["level"], "meaning": t["meaning"], "specialty": t["specialty"],
        "condition": t["condition"], "reason": t["reason"], "advice": t["advice"],
        "remedies": remedies, "profile": intake.profile, "language": intake.language,
    }
    game = CheckinGame(db, get_llm())
    case_id = game.start_case(t, intake.profile, intake.language)
    db.update_case(case_id, last_result=result)
    sessions.pop(sid, None)
    return {"done": True, "case_id": case_id, "result": result}


@app.get("/api/cases/latest")
def latest_case():
    case = db.latest_case()
    if case is None:
        return {"case": None}
    game = CheckinGame(db, None)
    return {"case": game.journey(case["id"]), "result": case.get("last_result") or {}}


@app.get("/api/cases/{case_id}/journey")
def journey(case_id: int):
    try:
        return CheckinGame(db, None).journey(case_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/cases/{case_id}/checkin")
def checkin(case_id: int, body: CheckinIn):
    if body.feeling not in FEELINGS:
        raise HTTPException(422, f"feeling must be one of {FEELINGS}")
    if db.get_case(case_id) is None:
        raise HTTPException(404, "Case not found")
    game = CheckinGame(db, get_llm())
    r = llm_call(game.check_in, case_id, body.feeling, body.score, body.quests_done, body.note)
    if r.get("retriaged") and r.get("triage"):
        last = dict(db.get_case(case_id).get("last_result") or {})
        t = r["triage"]
        last.update(level=t["level"], meaning=t["meaning"], specialty=t["specialty"],
                    condition=t["condition"] or last.get("condition"), reason=t["reason"], advice=t["advice"])
        db.update_case(case_id, last_result=last)
    return r


@app.get("/api/doctors")
def doctors(lat: float, lng: float, level: str = "yellow", specialty: str = "General Physician",
            radius: int = 5000):
    return find_doctors(level, specialty, lat, lng, radius)


# ---------------------------------------------------------------------------
# Serve the built React app (frontend/dist) from the same server.
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
