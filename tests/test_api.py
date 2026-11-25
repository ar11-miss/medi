"""API tests with a fake LLM and a temporary database."""
import importlib

import pytest
from fastapi.testclient import TestClient


class FakeLLM:
    def chat_json(self, system, messages, temperature=0.0):
        if "Information to collect" in system:
            if len(messages) == 1:
                return {"language": "en", "profile_update": {"symptoms": ["sore throat"]},
                        "next_question": "How long have you had it?"}
            return {"language": "en", "profile_update": {
                "duration_days": 1, "severity_score": 4, "age_years": 22, "sex": "male",
                "allergies": [], "current_medicines": [], "conditions": []}, "next_question": None}
        if "triage nurse" in system:
            return {"level": "green", "specialty": "General Physician", "condition": "sore throat",
                    "reason": "mild", "advice": "Gargle with warm salt water."}
        if "Candidates" in system:
            return {"id": "sore_throat", "confidence": 0.9}
        if "Grow your Tulsi" in system:
            return {"message": "Nice work!", "quests": [
                {"title": "Salt-water gargle", "emoji": "🧂", "kind": "care"},
                {"title": "Drink water", "emoji": "💧", "kind": "water"},
                {"title": "Rest", "emoji": "😴", "kind": "rest"}]}
        return {"summary": "Sore throat.", "home_care": ["Gargle"], "medicines":
                [{"id": "lozenges", "how_to_take": "1 every 3 hours", "note": ""}], "see_doctor_if": ["Fever"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAID_DB", str(tmp_path / "test.db"))
    import app.api as api
    api = importlib.reload(api)
    api._state["llm"] = FakeLLM()
    api._state["fast"] = FakeLLM()
    return TestClient(api.app), api


def test_full_flow(client):
    c, api = client
    assert c.get("/api/cases/latest").json() == {"case": None}

    sid = c.post("/api/symptoms/start").json()["session_id"]
    r = c.post(f"/api/symptoms/{sid}/message", json={"text": "my throat hurts"}).json()
    assert r["done"] is False and r["question"] == "How long have you had it?"
    r = c.post(f"/api/symptoms/{sid}/message", json={"text": "since yesterday, 22, male, nothing else"}).json()
    assert r["done"] is True
    res = r["result"]
    assert res["level"] == "green" and res["remedies"]["entry_id"] == "sore_throat"
    assert res["remedies"]["medicines"][0]["id"] == "lozenges"
    case_id = r["case_id"]

    latest = c.get("/api/cases/latest").json()
    assert latest["case"]["case_id"] == case_id and latest["result"]["condition"] == "sore throat"

    quests = latest["case"]["today_quests"]
    r = c.post(f"/api/cases/{case_id}/checkin",
               json={"feeling": "better", "score": 3, "quests_done": [q["id"] for q in quests]}).json()
    assert r["xp_gained"] > 0 and r["message"] == "Nice work!"
    assert c.get(f"/api/cases/{case_id}/journey").json()["xp"] == r["xp_total"]


def test_bad_inputs(client):
    c, _ = client
    assert c.post("/api/symptoms/nope/message", json={"text": "hi"}).status_code == 404
    assert c.post("/api/cases/999/checkin", json={"feeling": "better", "score": 3}).status_code == 404
    assert c.post("/api/cases/1/checkin", json={"feeling": "great", "score": 3}).status_code in (404, 422)


def test_groq_errors_become_readable(client):
    c, api = client

    class Broken:
        def chat_json(self, *a, **k):
            raise RuntimeError("Error code: 404 - model_not_found")

    api._state["llm"] = Broken()
    api._state["fast"] = Broken()
    sid = c.post("/api/symptoms/start").json()["session_id"]
    r = c.post(f"/api/symptoms/{sid}/message", json={"text": "fever"})
    assert r.status_code == 502 and "GROQ_MODEL" in r.json()["detail"]
