"""Step 3: Triage. The LLM reads the patient's information and returns a
severity level and the type of doctor to see, as JSON.

GenAI concepts shown here:
  - zero-shot classification with an LLM (no training, just instructions)
  - constrained structured output (level and specialty from fixed lists)
"""
import json

LEVELS = ["green", "yellow", "orange", "red"]

LEVEL_MEANING = {
    "green": "Minor problem. Can be managed at home.",
    "yellow": "See a doctor within 1-3 days.",
    "orange": "See a doctor today or within 24 hours.",
    "red": "Emergency. Call 108/112 or go to a hospital now.",
}

SPECIALTIES = [
    "General Physician", "Dermatologist", "ENT Specialist", "Gastroenterologist",
    "Pulmonologist", "Cardiologist", "Neurologist", "Orthopedic", "Ophthalmologist",
    "Dentist", "Gynecologist", "Pediatrician", "Urologist", "Psychiatrist",
    "Endocrinologist", "Emergency Department",
]

# Common ways the model may write a specialty -> our canonical name.
_SYNONYMS = {
    "gp": "General Physician", "general practitioner": "General Physician",
    "family doctor": "General Physician", "physician": "General Physician",
    "general medicine": "General Physician", "internal medicine": "General Physician",
    "skin specialist": "Dermatologist", "dermatology": "Dermatologist",
    "ent": "ENT Specialist", "otolaryngologist": "ENT Specialist", "ent doctor": "ENT Specialist",
    "gastroenterology": "Gastroenterologist",
    "chest physician": "Pulmonologist", "pulmonology": "Pulmonologist",
    "cardiology": "Cardiologist", "neurology": "Neurologist",
    "orthopaedic": "Orthopedic", "orthopedist": "Orthopedic", "orthopaedician": "Orthopedic",
    "orthopedic surgeon": "Orthopedic", "orthopaedic surgeon": "Orthopedic",
    "eye specialist": "Ophthalmologist", "ophthalmology": "Ophthalmologist",
    "dental": "Dentist", "dental surgeon": "Dentist",
    "gynaecologist": "Gynecologist", "obstetrician": "Gynecologist", "ob-gyn": "Gynecologist",
    "obgyn": "Gynecologist", "obstetrician/gynecologist": "Gynecologist",
    "paediatrician": "Pediatrician", "pediatrics": "Pediatrician", "child specialist": "Pediatrician",
    "urology": "Urologist", "psychiatry": "Psychiatrist",
    "endocrinology": "Endocrinologist", "diabetologist": "Endocrinologist",
    "emergency": "Emergency Department", "emergency room": "Emergency Department",
    "er": "Emergency Department", "hospital emergency": "Emergency Department",
    "casualty": "Emergency Department",
}

SYSTEM_PROMPT = """You are MediAid, an experienced triage nurse in India. Read the patient's
information and decide how urgently they need medical care.

Severity levels (choose exactly one):
- "green": minor problem that can be managed at home with rest and simple care
- "yellow": should see a doctor within 1-3 days; not urgent
- "orange": should see a doctor today or within 24 hours, often a specialist
- "red": emergency; must call 108/112 or go to a hospital emergency department now

Choose the specialty from this list ONLY:
__SPECIALTIES__
Use "Emergency Department" for red. Use "General Physician" for green, and when no
specialist clearly fits.

Reply ONLY with JSON in this format:
{
  "level": "green" | "yellow" | "orange" | "red",
  "specialty": "one name from the list",
  "condition": "short name of the likely problem, e.g. 'common cold', 'skin infection'",
  "reason": "one sentence in English explaining why you chose this level",
  "advice": "one or two short sentences for the patient, written in __LANGUAGE__"
}"""


def normalise_level(value) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in LEVELS else None


def normalise_specialty(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().lower().rstrip(".")
    candidates = [v, v[:-1] if v.endswith("s") else v]   # "dermatologists" -> "dermatologist"
    for c in candidates:
        for name in SPECIALTIES:
            if c == name.lower():
                return name
        if c in _SYNONYMS:
            return _SYNONYMS[c]
    return None


def build_prompt(language: str | None) -> str:
    lang = {"en": "English", "hi": "Hindi", "mr": "Marathi"}.get(
        language or "", "the same language and script the patient used")
    return (SYSTEM_PROMPT
            .replace("__SPECIALTIES__", ", ".join(SPECIALTIES))
            .replace("__LANGUAGE__", lang))


def triage(llm, text: str | None = None, profile: dict | None = None,
           language: str | None = None) -> dict:
    """Classify a patient. Pass free text, a profile from intake, or both."""
    parts = []
    if profile:
        parts.append("Patient profile (JSON):\n" + json.dumps(profile, ensure_ascii=False, indent=2))
    if text:
        parts.append("Patient's own words:\n" + text)
    if not parts:
        raise ValueError("triage() needs text or a profile")

    raw = llm.chat_json(build_prompt(language), [{"role": "user", "content": "\n\n".join(parts)}])

    level = normalise_level(raw.get("level"))
    specialty = normalise_specialty(raw.get("specialty"))
    return {
        "level": level,
        "specialty": specialty,
        "condition": raw.get("condition"),
        "reason": raw.get("reason"),
        "advice": raw.get("advice"),
        "meaning": LEVEL_MEANING.get(level),
        "valid": level is not None,
        "raw": raw,
    }
