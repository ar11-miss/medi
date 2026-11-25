"""Step 6: Remedies with RAG (Retrieval-Augmented Generation).

    patient's words + profile + triage
            │
    1. RETRIEVE  top-3 entries from the knowledge base (TF-IDF over character
                 n-grams, works across English, Hindi and Marathi; plus
                 multilingual embeddings if sentence-transformers is installed)
            │
    2. RE-RANK   Groq reads the 3 candidates and picks the one that matches,
                 or "none" if nothing fits
            │
    3. PERSONALISE  remove medicines this patient shouldn't take (age,
                 pregnancy, allergies, illnesses, medicines they already take)
            │
    4. GENERATE  Groq writes the answer in the patient's language using ONLY
                 the retrieved entry
            │
    5. GROUNDING CHECK  any medicine Groq names that is not in the entry is dropped

GenAI concepts shown here: RAG, sparse + dense retrieval, LLM re-ranking,
context injection, grounded generation, hallucination check.
"""
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "remedies_kb.json"
LANG_NAME = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_SCORE = 0.14   # backup only: below this TF-IDF score the no-LLM path says "no match"

CHILD_NOTE = {
    "en": "For children, ask a pharmacist or doctor for the right medicine dose by weight.",
    "hi": "बच्चों के लिए दवा की सही खुराक वज़न के हिसाब से फार्मासिस्ट या डॉक्टर से पूछें।",
    "mr": "मुलांसाठी औषधाचा योग्य डोस वजनानुसार फार्मासिस्ट किंवा डॉक्टरांना विचारा.",
}


def load_kb(path: Path | str = KB_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def doc_text(entry: dict) -> str:
    return " . ".join([entry["name"], entry["description"], " , ".join(entry["keywords"])])


def build_query(text: str | None = None, profile: dict | None = None, triage: dict | None = None) -> str:
    parts = [text or ""]
    if profile:
        parts += list(profile.get("symptoms") or [])
    if triage and triage.get("condition"):
        parts.append(str(triage["condition"]))
    return " . ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 1. Retrieval
# ---------------------------------------------------------------------------
class Retriever:
    """mode: 'tfidf', 'hybrid' (TF-IDF + embeddings), or 'auto' (hybrid if available)."""

    def __init__(self, kb: dict, mode: str = "auto"):
        self.entries = kb["entries"]
        docs = [doc_text(e) for e in self.entries]
        # character n-grams handle Hindi/Marathi word endings and spelling variants
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, lowercase=True)
        self.matrix = self.vec.fit_transform(docs)
        self.encoder = None
        self.doc_emb = None
        if mode in ("auto", "hybrid"):
            try:
                from sentence_transformers import SentenceTransformer
                self.encoder = SentenceTransformer(EMBED_MODEL)
                self.doc_emb = self.encoder.encode(docs, normalize_embeddings=True)
            except Exception:  # noqa: BLE001 - package missing or model download failed
                if mode == "hybrid":
                    raise
        self.mode = "hybrid" if self.encoder is not None else "tfidf"

    def search(self, query: str, k: int = 3) -> list[dict]:
        sparse = cosine_similarity(self.vec.transform([query]), self.matrix)[0]
        order = list(sparse.argsort()[::-1])
        if self.encoder is not None:
            dense = self.doc_emb @ self.encoder.encode([query], normalize_embeddings=True)[0]
            dense_order = list(dense.argsort()[::-1])
            # reciprocal rank fusion of the two rankings
            rrf = {i: 1 / (60 + order.index(i)) + 1 / (60 + dense_order.index(i)) for i in range(len(self.entries))}
            order = sorted(rrf, key=rrf.get, reverse=True)
        return [{"id": self.entries[i]["id"], "name": self.entries[i]["name"],
                 "score": round(float(sparse[i]), 4), "entry": self.entries[i]} for i in order[:k]]


# ---------------------------------------------------------------------------
# 2. Re-rank with Groq
# ---------------------------------------------------------------------------
SELECT_PROMPT = """You match a patient's health problem to entries in a medical knowledge base.
Read the patient's description and the candidate entries. Choose the ONE entry that matches the
patient's MAIN problem. If none of them matches well, answer "none". Do not guess.

Candidates:
{candidates}

Reply ONLY with JSON: {{"id": "<candidate id or none>", "confidence": <number from 0 to 1>}}"""


def select_entry(llm, query: str, candidates: list[dict]) -> tuple[dict | None, float, str]:
    """Returns (entry or None, confidence, how it was chosen)."""
    if llm is not None:
        lines = "\n".join(f"- id: {c['id']} | {c['name']}: {c['entry']['description']}" for c in candidates)
        try:
            out = llm.chat_json(SELECT_PROMPT.format(candidates=lines),
                                [{"role": "user", "content": f"Patient: {query}"}])
            chosen = str(out.get("id", "")).strip()
            conf = float(out.get("confidence") or 0)
            if chosen == "none":
                return None, conf, "groq"
            for c in candidates:
                if c["id"] == chosen:
                    return c["entry"], conf, "groq"
        except Exception:  # noqa: BLE001 - fall back to retrieval score
            pass
    top = candidates[0] if candidates else None
    if top and top["score"] >= MIN_SCORE:
        return top["entry"], top["score"], "retrieval"
    return None, 0.0, "retrieval"


# ---------------------------------------------------------------------------
# 3. Personalise: which medicines suit this patient
# ---------------------------------------------------------------------------
def _hits(items, terms) -> str | None:
    for item in items or []:
        a = str(item).lower().strip()
        for term in terms or []:
            b = term.lower()
            if a and (a in b or b in a):
                return str(item)
    return None


def personalise(entry: dict, kb: dict, profile: dict | None, language: str = "en") -> dict:
    profile = profile or {}
    age = profile.get("age_years")
    allowed, excluded, notes = [], [], []
    if age is None and entry["medicines"]:
        notes.append("Age not known, so no medicines are suggested. Tell MediAid your age for medicine advice.")
    for key in entry["medicines"]:
        m = kb["medicines"][key]
        reason = None
        if age is None:
            reason = "age not known"
        elif age < m["min_age"]:
            reason = f"not for under {m['min_age']} years"
        elif profile.get("pregnant") and m["pregnancy"] == "avoid":
            reason = "not advised in pregnancy"
        elif hit := _hits(profile.get("allergies"), m["allergy_names"]):
            reason = f"you are allergic to {hit}"
        elif hit := _hits(profile.get("conditions"), m["avoid_if"]):
            reason = f"not advised with {hit}"
        elif hit := _hits(profile.get("current_medicines"), m["interacts_with"]):
            reason = f"may not mix with {hit}, which you already take"
        if reason:
            excluded.append({"id": key, "name": m["name"], "reason": reason})
            continue
        note = ""
        if profile.get("pregnant") and m["pregnancy"] == "caution":
            note = "You are pregnant: check with your doctor before taking this."
        allowed.append({"id": key, "name": m["name"], "use": m["use"], "dose": m["adult_dose"], "note": note})
    if age is not None and age < 12:
        notes.append(CHILD_NOTE.get(language, CHILD_NOTE["en"]))
    return {"allowed": allowed, "excluded": excluded, "notes": notes}


# ---------------------------------------------------------------------------
# 4 + 5. Generate from the entry only, then check grounding
# ---------------------------------------------------------------------------
ANSWER_PROMPT = """You are MediAid, a kind nurse. Answer the patient using ONLY the knowledge-base
entry below. Do not add any medicine, dose or advice that is not in it.

Severity level from triage: {level} ({level_meaning})
Patient summary: {patient}

KNOWLEDGE-BASE ENTRY: {name}
Home care:
{home_care}
Medicines this patient may use (use ONLY these ids):
{medicines}
See a doctor if:
{see_doctor}

Write everything in {language}, in simple words. Keep each point short.
Reply ONLY with JSON:
{{"summary": "2 sentences: what this likely is and what to do{yellow_hint}",
  "home_care": ["..."],
  "medicines": [{{"id": "<id from the list>", "how_to_take": "the dose, in {language}", "note": "short note or empty"}}],
  "see_doctor_if": ["..."]}}"""

LEVEL_MEANING = {"green": "minor, can be managed at home", "yellow": "see a doctor within 1-3 days"}


def _patient_summary(profile: dict | None) -> str:
    p = profile or {}
    bits = []
    if p.get("age_years") is not None:
        bits.append(f"age {p['age_years']:g}")
    if p.get("sex"):
        bits.append(p["sex"])
    if p.get("pregnant"):
        bits.append("pregnant")
    if p.get("symptoms"):
        bits.append("symptoms: " + ", ".join(p["symptoms"]))
    if p.get("duration_days") is not None:
        bits.append(f"for {p['duration_days']:g} day(s)")
    return "; ".join(bits) or "not given"


def generate_answer(llm, entry: dict, personal: dict, profile: dict | None, level: str, language: str) -> dict:
    meds = "\n".join(f"- id: {m['id']} | {m['name']} | for {m['use']} | dose: {m['dose']}"
                     + (f" | note: {m['note']}" if m["note"] else "") for m in personal["allowed"]) or "(none)"
    prompt = ANSWER_PROMPT.format(
        level=level, level_meaning=LEVEL_MEANING.get(level, ""), patient=_patient_summary(profile),
        name=entry["name"], home_care="\n".join(f"- {h}" for h in entry["home_care"]), medicines=meds,
        see_doctor="\n".join(f"- {s}" for s in entry["see_doctor_if"]),
        language=LANG_NAME.get(language, "English"),
        yellow_hint="; say they should see a doctor within 1-3 days" if level == "yellow" else "")
    out = llm.chat_json(prompt, [{"role": "user", "content": "Write the advice for this patient."}], temperature=0.2)

    allowed = {m["id"]: m for m in personal["allowed"]}
    medicines, dropped = [], []
    for m in out.get("medicines") or []:
        mid = str((m or {}).get("id", "")).strip()
        if mid in allowed:
            medicines.append({"id": mid, "name": allowed[mid]["name"],
                              "how_to_take": m.get("how_to_take") or allowed[mid]["dose"],
                              "note": m.get("note") or allowed[mid]["note"]})
        else:
            dropped.append(mid or str(m))
    return {
        "summary": str(out.get("summary") or ""),
        "home_care": [str(x) for x in out.get("home_care") or entry["home_care"]],
        "medicines": medicines,
        "see_doctor_if": [str(x) for x in out.get("see_doctor_if") or entry["see_doctor_if"]],
        "ungrounded_dropped": dropped,
        "generated_by": "groq",
    }


def template_answer(entry: dict, personal: dict, level: str) -> dict:
    """Used when Groq is unavailable: the entry itself, in English."""
    summary = f"This looks like {entry['name'].lower()}. " + (
        "You can manage it at home." if level == "green" else "Please see a doctor within 1-3 days.")
    return {
        "summary": summary, "home_care": entry["home_care"],
        "medicines": [{"id": m["id"], "name": m["name"], "how_to_take": m["dose"], "note": m["note"]}
                      for m in personal["allowed"]],
        "see_doctor_if": entry["see_doctor_if"], "ungrounded_dropped": [], "generated_by": "template",
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
class RemedyRAG:
    def __init__(self, llm=None, kb_path: Path | str = KB_PATH, retrieval_mode: str = "auto"):
        self.llm = llm
        self.kb = load_kb(kb_path)
        self.retriever = Retriever(self.kb, retrieval_mode)

    def get_remedies(self, text: str | None = None, profile: dict | None = None, triage: dict | None = None,
                     language: str = "en", k: int = 3) -> dict:
        level = (triage or {}).get("level") or "green"
        if level in ("orange", "red"):
            return {"matched": False, "skipped": True, "level": level,
                    "summary": "No home remedies for this level. Please see a doctor"
                               + (" now." if level == "red" else " today.")}

        query = build_query(text, profile, triage)
        candidates = self.retriever.search(query, k)
        entry, confidence, chosen_by = select_entry(self.llm, query, candidates)
        base = {"level": level, "query": query, "retrieval_mode": self.retriever.mode, "chosen_by": chosen_by,
                "candidates": [{"id": c["id"], "name": c["name"], "score": c["score"]} for c in candidates]}
        if entry is None:
            return {**base, "matched": False, "skipped": False, "confidence": confidence,
                    "summary": "MediAid doesn't have home-care advice for this problem. "
                               "Please see a General Physician."}

        personal = personalise(entry, self.kb, profile, language)
        answer = None
        if self.llm is not None:
            try:
                answer = generate_answer(self.llm, entry, personal, profile, level, language)
            except Exception:  # noqa: BLE001 - fall back to the plain entry
                answer = None
        answer = answer or template_answer(entry, personal, level)
        return {**base, "matched": True, "skipped": False, "confidence": confidence,
                "entry_id": entry["id"], "entry_name": entry["name"],
                "source": f"MediAid knowledge base: {entry['name']}",
                "excluded_medicines": personal["excluded"], "notes": personal["notes"], **answer}
