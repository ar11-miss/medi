"""Intake tests with a fake LLM, so they run without a Groq key."""
from app.intake import IntakeSession, merge_profile, missing_fields, EMPTY_PROFILE


class FakeLLM:
    """Returns pre-written replies in order and records what it was sent."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat_json(self, system, messages, temperature=0.0):
        self.calls.append((system, list(messages)))
        return self.replies.pop(0)


def test_full_conversation_reaches_done():
    llm = FakeLLM([
        {"language": "en", "profile_update": {"symptoms": ["fever", "headache"], "duration_days": 2},
         "next_question": "How bad is it from 1 to 10?"},
        {"language": "en", "profile_update": {"severity_score": 5}, "next_question": "How old are you, and are you male or female?"},
        {"language": "en", "profile_update": {"age_years": 21, "sex": "male"}, "next_question": "Any allergies?"},
        {"language": "en", "profile_update": {"allergies": [], "current_medicines": [], "conditions": []}, "next_question": None},
    ])
    s = IntakeSession(llm)
    assert s.step("I have fever and headache since 2 days")["question"] == "How bad is it from 1 to 10?"
    s.step("5")
    s.step("21, male")
    result = s.step("no allergies, no medicines, no illness")
    assert result["done"] is True
    assert s.profile["symptoms"] == ["fever", "headache"]
    assert s.profile["allergies"] == []
    # conversation memory: the last call carried the whole chat
    assert len(llm.calls[-1][1]) == 7


def test_pregnancy_asked_only_for_women_12_to_50():
    p = merge_profile(EMPTY_PROFILE, {"symptoms": ["nausea"], "duration_days": 1, "severity_score": 4,
                                      "age_years": 25, "sex": "female", "allergies": [],
                                      "current_medicines": [], "conditions": []})
    assert missing_fields(p) == ["pregnant"]
    p_male = dict(p, sex="male")
    assert missing_fields(p_male) == []
    p_older = dict(p, age_years=60)
    assert missing_fields(p_older) == []


def test_fallback_question_in_users_language():
    llm = FakeLLM([{"language": "mr", "profile_update": {"symptoms": ["ताप"]}, "next_question": None}])
    result = IntakeSession(llm).step("मला ताप आहे")
    assert result["question"] == "हे किती दिवसांपासून आहे?"


def test_cleans_model_slips():
    p = merge_profile(EMPTY_PROFILE, {"temperature_c": 102, "severity_score": "15",
                                      "allergies": "none", "symptoms": "cough", "sex": "M"})
    assert p["temperature_c"] == 38.9          # 102 °F converted
    assert p["severity_score"] == 10           # clamped
    assert p["allergies"] == []                # "none" -> empty list
    assert p["symptoms"] == ["cough"]          # string -> list
    assert p["sex"] is None                    # invalid value ignored


def test_lists_merge_without_duplicates():
    p = merge_profile(EMPTY_PROFILE, {"symptoms": ["cough"]})
    p = merge_profile(p, {"symptoms": ["Cough", "sore throat"]})
    assert p["symptoms"] == ["cough", "sore throat"]


def test_stops_after_max_questions():
    llm = FakeLLM([{"language": "en", "profile_update": {}, "next_question": "Tell me more?"}] * 4)
    s = IntakeSession(llm, max_questions=3)
    for _ in range(3):
        assert s.step("hmm")["done"] is False
    assert s.step("hmm")["done"] is True
