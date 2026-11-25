"""Step 3: Intake. The LLM acts as a nurse, asks follow-up questions one at a
time, and fills in a structured patient profile (JSON).

GenAI concepts shown here:
  - system prompt / role prompting (the nurse persona)
  - conversation memory (full chat history is sent every turn)
  - structured output (the model must reply in a fixed JSON format)
  - multilingual generation (replies in the user's language)
"""
import json

# Fields we need before triage. null = not known yet, [] = user said "none".
EMPTY_PROFILE = {
    "symptoms": [],
    "duration_days": None,
    "severity_score": None,   # 1-10, how bad the user says it is
    "age_years": None,
    "sex": None,              # "male" | "female" | "other"
    "pregnant": None,         # only asked for women aged 12-50
    "temperature_c": None,    # only if they mention fever
    "allergies": None,
    "current_medicines": None,
    "conditions": None,       # long-term conditions: diabetes, BP, asthma...
}

REQUIRED = ["symptoms", "duration_days", "severity_score", "age_years", "sex",
            "allergies", "current_medicines", "conditions"]

SYSTEM_PROMPT = """You are MediAid, a kind and calm nurse assistant. You are talking to a patient
who describes their symptoms. Your job right now is ONLY to collect information.
Do not diagnose, do not suggest medicines, do not give advice yet.

Information to collect:
- main symptoms
- how long they have had them (convert to days, e.g. "since yesterday" = 1, "2 weeks" = 14)
- how bad it is on a scale of 1 to 10
- age and sex
- if the patient is female and aged 12-50: whether she is or could be pregnant
- body temperature, only if they have fever (convert Fahrenheit to Celsius)
- allergies to any medicine
- medicines they are taking now
- long-term conditions (diabetes, blood pressure, asthma, heart, kidney, liver...)

Rules:
- Ask ONE short, friendly question at a time about what is still missing. To keep it quick,
  you may ask about two related things together (for example "How old are you, and are you
  male or female?" or "Any allergies, or medicines you take now?").
- Reply in the same language and script the patient uses: English, Hindi or Marathi
  (Devanagari), or the same Roman-script mix if they write like that.
- If the patient says "no" or "none" for allergies, medicines or conditions, record an empty list [].
- Write all profile values in English, even when the patient writes in Hindi or Marathi
  (for example ताप -> "fever", मधुमेह -> "diabetes", क्रोसिन -> "Crocin").
- Keep anything you don't know as null. Never guess.

Profile collected so far:
{profile}

Reply ONLY with JSON in exactly this format:
{{
  "language": "en" or "hi" or "mr",
  "profile_update": {{ only the fields you learned from the patient's latest message, using the same keys as the profile }},
  "next_question": "your next question to the patient, or null if nothing is missing"
}}"""

# Used if the model forgets to ask a question.
FALLBACK_QUESTIONS = {
    "symptoms": {"en": "What symptoms are you having?", "hi": "आपको क्या तकलीफ़ हो रही है?", "mr": "तुम्हाला काय त्रास होत आहे?"},
    "duration_days": {"en": "How long have you had this?", "hi": "यह कब से है?", "mr": "हे किती दिवसांपासून आहे?"},
    "severity_score": {"en": "On a scale of 1 to 10, how bad is it?", "hi": "1 से 10 में, तकलीफ़ कितनी ज़्यादा है?", "mr": "1 ते 10 मध्ये, त्रास किती आहे?"},
    "age_years": {"en": "How old are you?", "hi": "आपकी उम्र क्या है?", "mr": "तुमचे वय किती आहे?"},
    "sex": {"en": "Are you male or female?", "hi": "आप पुरुष हैं या महिला?", "mr": "तुम्ही पुरुष आहात की स्त्री?"},
    "pregnant": {"en": "Are you pregnant, or could you be?", "hi": "क्या आप गर्भवती हैं या हो सकती हैं?", "mr": "तुम्ही गर्भवती आहात का, किंवा असू शकता का?"},
    "allergies": {"en": "Are you allergic to any medicine?", "hi": "क्या आपको किसी दवा से एलर्जी है?", "mr": "तुम्हाला कोणत्या औषधाची ॲलर्जी आहे का?"},
    "current_medicines": {"en": "Are you taking any medicines right now?", "hi": "क्या आप अभी कोई दवा ले रहे हैं?", "mr": "तुम्ही सध्या कोणते औषध घेत आहात का?"},
    "conditions": {"en": "Do you have any long-term illness like diabetes, BP or asthma?", "hi": "क्या आपको डायबिटीज़, बीपी या अस्थमा जैसी कोई पुरानी बीमारी है?", "mr": "तुम्हाला मधुमेह, बीपी किंवा दमा असा कोणता जुना आजार आहे का?"},
}


def missing_fields(p: dict) -> list[str]:
    missing = [f for f in REQUIRED if p.get(f) in (None, [])]
    # "none" answers are stored as [] and count as known, except symptoms
    missing = [f for f in missing if not (f != "symptoms" and p.get(f) == [])]
    age = p.get("age_years")
    if p.get("sex") == "female" and age is not None and 12 <= age <= 50 and p.get("pregnant") is None:
        missing.append("pregnant")
    return missing


def _clean(update: dict) -> dict:
    """Fix common model slips: wrong types, Fahrenheit, out-of-range scores."""
    out = {}
    for key, val in update.items():
        if key not in EMPTY_PROFILE or val is None:
            continue
        try:
            if key in ("duration_days", "age_years", "temperature_c"):
                val = float(val)
                if key == "temperature_c" and val > 45:      # looks like Fahrenheit
                    val = round((val - 32) * 5 / 9, 1)
            elif key == "severity_score":
                val = max(1, min(10, int(float(val))))
            elif key in ("symptoms", "allergies", "current_medicines", "conditions"):
                if isinstance(val, str):
                    val = [val]
                val = [str(v).strip() for v in val if str(v).strip()
                       and str(v).strip().lower() not in ("none", "no", "nil")]
            elif key == "sex":
                val = str(val).lower()
                if val not in ("male", "female", "other"):
                    continue
            elif key == "pregnant":
                val = bool(val)
        except (TypeError, ValueError):
            continue
        out[key] = val
    return out


def merge_profile(profile: dict, update: dict) -> dict:
    merged = dict(profile)
    for key, val in _clean(update).items():
        if isinstance(val, list):
            old = merged.get(key) or []
            seen = {v.lower() for v in old}
            merged[key] = old + [v for v in val if v.lower() not in seen]
        else:
            merged[key] = val
    return merged


class IntakeSession:
    def __init__(self, llm, max_questions: int = 6):
        self.llm = llm
        self.max_questions = max_questions
        self.messages: list[dict] = []
        self.profile = json.loads(json.dumps(EMPTY_PROFILE))
        self.language = "en"
        self.questions_asked = 0
        self.done = False

    def step(self, user_text: str) -> dict:
        """Process one patient message. Returns the next question, or done=True."""
        self.messages.append({"role": "user", "content": user_text})
        system = SYSTEM_PROMPT.format(profile=json.dumps(self.profile, ensure_ascii=False, indent=2))
        result = self.llm.chat_json(system, self.messages)

        if result.get("language") in ("en", "hi", "mr"):
            self.language = result["language"]
        self.profile = merge_profile(self.profile, result.get("profile_update") or {})

        missing = missing_fields(self.profile)
        if not missing or self.questions_asked >= self.max_questions:
            self.done = True
            return {"done": True, "question": None, "profile": self.profile, "language": self.language}

        question = result.get("next_question") or FALLBACK_QUESTIONS[missing[0]][self.language]
        self.questions_asked += 1
        self.messages.append({"role": "assistant", "content": question})
        return {"done": False, "question": question, "profile": self.profile, "language": self.language}
