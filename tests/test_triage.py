"""Triage and metrics tests with a fake LLM (no Groq key needed)."""
import csv

from app.metrics import summarise
from app.triage import LEVELS, SPECIALTIES, normalise_specialty, triage


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.system = None
        self.messages = None

    def chat_json(self, system, messages, temperature=0.0):
        self.system, self.messages = system, messages
        return self.reply


def test_triage_returns_clean_level_and_specialty():
    llm = FakeLLM({"level": "Yellow", "specialty": "skin specialist", "condition": "fungal infection",
                   "reason": "Spreading rash for 2 weeks.", "advice": "See a doctor in 1-3 days."})
    r = triage(llm, text="Itchy ring-shaped rash for 2 weeks")
    assert r["level"] == "yellow" and r["valid"]
    assert r["specialty"] == "Dermatologist"
    assert "Dermatologist" in llm.system and "JSON" in llm.system


def test_invalid_level_is_flagged():
    r = triage(FakeLLM({"level": "urgent", "specialty": "GP"}), text="fever")
    assert r["level"] is None and r["valid"] is False
    assert r["specialty"] == "General Physician"


def test_profile_is_sent_to_model():
    llm = FakeLLM({"level": "green", "specialty": "General Physician"})
    triage(llm, profile={"symptoms": ["cold"], "age_years": 24})
    assert '"age_years": 24' in llm.messages[0]["content"]


def test_specialty_synonyms():
    assert normalise_specialty("ENT") == "ENT Specialist"
    assert normalise_specialty("Paediatrician") == "Pediatrician"
    assert normalise_specialty("Orthopaedic surgeon") == "Orthopedic"
    assert normalise_specialty("emergency room") == "Emergency Department"
    assert normalise_specialty("Astrologer") is None


def _row(g, p, lang="en", gs="General Physician", ps="General Physician"):
    return {"gold_level": g, "pred_level": p, "language": lang,
            "gold_specialty": gs, "pred_specialty": ps, "latency_s": 1.0}


def test_metrics_on_known_example():
    rows = [
        _row("green", "green"), _row("yellow", "green"),          # 1 under-triage
        _row("orange", "red"),                                    # 1 over-triage
        _row("red", "red"), _row("red", "yellow"),                # 1 severe under-triage
        _row("yellow", "yellow", gs="Dermatologist", ps="Dermatologist"),
        _row("orange", "invalid", lang="hi"),
    ]
    s = summarise(rows)
    assert s["n"] == 7
    assert abs(s["accuracy"] - 3 / 7) < 1e-9
    assert abs(s["under_triage_rate"] - 2 / 7) < 1e-9
    assert abs(s["over_triage_rate"] - 1 / 7) < 1e-9
    assert s["severe_under_triage"] == 1
    assert s["emergency_recall"] == 0.5
    assert s["invalid_outputs"] == 1
    assert s["confusion"][2][4] == 1          # orange -> invalid column
    assert s["by_language"]["hi"]["accuracy"] == 0.0


def test_dataset_is_valid_and_balanced():
    with open("data/test_cases.csv", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
    assert len(cases) == 60
    for c in cases:
        assert c["gold_level"] in LEVELS
        assert c["gold_specialty"] in SPECIALTIES
        assert c["language"] in ("en", "hi", "mr")
    for lang in ("en", "hi", "mr"):
        for lvl in LEVELS:
            assert sum(c["language"] == lang and c["gold_level"] == lvl for c in cases) == 5
