"""Gamified daily check-in: "Grow your Tulsi".

Each day the patient answers 3 quick things: how they feel (better/same/worse),
a symptom score (1-10), and which of yesterday's 3 quests they finished.
They earn XP, keep a streak, unlock badges, and their Tulsi plant grows.
The LLM writes a short encouraging message and tomorrow's quests, tailored
to their illness and language. If they get worse, triage runs again.

GenAI concepts shown here:
  - personalised content generation (messages + quests per patient)
  - context injection (streak, progress and history go into the prompt)
  - re-running LLM triage on new information
"""
from datetime import date

from app.triage import triage

FEELINGS = ("better", "same", "worse")

# ---- Points ---------------------------------------------------------------
XP_CHECKIN = 10          # for showing up
XP_BETTER = 10           # extra if feeling better
XP_QUEST = 5             # per quest finished
XP_ALL_QUESTS = 10       # bonus for finishing all 3
XP_STREAK_BONUS = 15     # every 3rd day in a row

# ---- Tulsi plant grows with XP --------------------------------------------
PLANT_STAGES = [  # (min XP, key, emoji, English, Hindi, Marathi)
    (0, "seed", "🌰", "Seed", "बीज", "बी"),
    (30, "sprout", "🌱", "Sprout", "अंकुर", "अंकुर"),
    (80, "young", "🌿", "Young Tulsi", "छोटी तुलसी", "छोटी तुळस"),
    (150, "bushy", "🪴", "Bushy Tulsi", "घनी तुलसी", "दाट तुळस"),
    (250, "flowering", "🌸", "Flowering Tulsi", "फूलों वाली तुलसी", "मंजिरी आलेली तुळस"),
]

# ---- Badges ---------------------------------------------------------------
BADGES = {
    "first_step": ("👣", "First Step", "Did your first check-in"),
    "streak_3": ("🔥", "On Fire", "3 days in a row"),
    "streak_7": ("🏆", "Week Warrior", "7 days in a row"),
    "quest_champion": ("⭐", "Quest Champion", "Finished all 3 quests in one day"),
    "hydration_hero": ("💧", "Hydration Hero", "Finished 3 water quests"),
    "rest_master": ("😴", "Rest Master", "Finished 3 rest quests"),
    "honest_heart": ("💙", "Honest Heart", "Told MediAid when you felt worse"),
    "comeback": ("📈", "Comeback", "Felt better after a worse day"),
    "recovered": ("🎉", "Recovered!", "Symptom score down to 1-2 and feeling better"),
}

QUEST_KINDS = ("water", "rest", "care", "track", "move", "food")

DEFAULT_QUESTS = {
    "en": [("Drink 8 glasses of water", "💧", "water"), ("Sleep at least 8 hours", "😴", "rest"),
           ("Note how you feel tonight", "📝", "track")],
    "hi": [("8 गिलास पानी पिएँ", "💧", "water"), ("कम से कम 8 घंटे सोएँ", "😴", "rest"),
           ("रात को अपनी तबीयत नोट करें", "📝", "track")],
    "mr": [("8 ग्लास पाणी प्या", "💧", "water"), ("किमान 8 तास झोपा", "😴", "rest"),
           ("रात्री तब्येत कशी आहे ते नोंदवा", "📝", "track")],
}

FALLBACK_MESSAGE = {
    "better": {"en": "Great to hear you're feeling better! Keep it up.",
               "hi": "यह सुनकर अच्छा लगा कि आप बेहतर महसूस कर रहे हैं! ऐसे ही जारी रखें।",
               "mr": "तुम्हाला बरं वाटतंय हे ऐकून छान वाटलं! असंच चालू ठेवा."},
    "same": {"en": "Thanks for checking in. Rest well and keep going.",
             "hi": "चेक-इन के लिए धन्यवाद। आराम करें और जारी रखें।",
             "mr": "चेक-इन केल्याबद्दल धन्यवाद. आराम करा आणि असंच चालू ठेवा."},
    "worse": {"en": "Sorry you're feeling worse. Thank you for telling me.",
              "hi": "मुझे दुख है कि आपकी तबीयत बिगड़ी है। बताने के लिए धन्यवाद।",
              "mr": "तब्येत बिघडली हे ऐकून वाईट वाटलं. सांगितल्याबद्दल धन्यवाद."},
}

# After this many days without feeling better, triage runs again.
REVIEW_AFTER_DAYS = {"green": 3, "yellow": 5, "orange": 2, "red": 1}

LANG_NAME = {"en": "English", "hi": "Hindi", "mr": "Marathi"}

CHECKIN_PROMPT = """You are MediAid, a cheerful and caring nurse coach running a daily recovery
check-in game called "Grow your Tulsi". Every check-in helps the patient's Tulsi plant grow.

Patient's problem: {condition}
Current severity level: {level}
Recovery day: {day}
Feeling today: {feeling}
Symptom score today: {score}/10 (day 1 was {first}/10)
Check-in streak: {streak} days
Tulsi plant stage: {plant}
Patient's note: {note}

Write in {language}:
1. "message": 2-3 short, warm sentences. Mention their streak or progress. If they feel worse,
   be kind, thank them for being honest, and do not blame them.
2. "quests": exactly 3 small self-care tasks for tomorrow that fit this problem. Simple, everyday
   actions only, like drinking water, resting, a warm salt-water gargle, a short walk, eating light
   food, or noting their temperature. Do not mention any medicine. Each quest has:
   "title" (at most 8 words, in {language}), "emoji" (one emoji), and
   "kind" (one of: water, rest, care, track, move, food).

Reply ONLY with JSON:
{{"message": "...", "quests": [{{"title": "...", "emoji": "...", "kind": "..."}}]}}"""


# ---------------------------------------------------------------------------
def plant_for(xp: int, language: str = "en") -> dict:
    stage_idx = max(i for i, s in enumerate(PLANT_STAGES) if xp >= s[0])
    s = PLANT_STAGES[stage_idx]
    nxt = PLANT_STAGES[stage_idx + 1][0] if stage_idx + 1 < len(PLANT_STAGES) else None
    name = {"en": s[3], "hi": s[4], "mr": s[5]}.get(language, s[3])
    return {"stage": stage_idx, "key": s[1], "emoji": s[2], "name": name,
            "xp": xp, "next_stage_xp": nxt,
            "progress": 1.0 if nxt is None else (xp - s[0]) / (nxt - s[0])}


def streak_on(days: list[date], today: date) -> int:
    """Consecutive days with a check-in, ending today."""
    have = set(days)
    n, d = 0, today
    while d in have:
        n += 1
        d = date.fromordinal(d.toordinal() - 1)
    return n


def make_quests(items: list, day: date) -> list[dict]:
    out = []
    for i, q in enumerate(items[:3], 1):
        if isinstance(q, dict):
            title, emoji, kind = q.get("title"), q.get("emoji") or "✅", q.get("kind")
        else:
            title, emoji, kind = q
        if not title:
            continue
        out.append({"id": f"{day.isoformat()}-q{i}", "title": str(title)[:80], "emoji": str(emoji)[:4],
                    "kind": kind if kind in QUEST_KINDS else "care"})
    return out


def badge_info(key: str) -> dict:
    e, name, desc = BADGES[key]
    return {"key": key, "emoji": e, "name": name, "description": desc}


class CheckinGame:
    def __init__(self, db, llm):
        self.db = db
        self.llm = llm

    # ----- start tracking a new health problem, right after triage -----------
    def start_case(self, triage_result: dict, profile: dict, language: str = "en",
                   today: date | None = None) -> int:
        today = today or date.today()
        quests = make_quests(DEFAULT_QUESTS.get(language, DEFAULT_QUESTS["en"]), today)
        return self.db.create_case(
            start_day=today, language=language, profile=profile or {},
            condition=triage_result.get("condition"), level=triage_result.get("level") or "yellow",
            specialty=triage_result.get("specialty"),
            first_score=int((profile or {}).get("severity_score") or 5), quests=quests)

    # ----- the daily check-in --------------------------------------------------
    def check_in(self, case_id: int, feeling: str, score: int, quests_done: list[str] | None = None,
                 note: str = "", today: date | None = None) -> dict:
        today = today or date.today()
        case = self.db.get_case(case_id)
        if case is None:
            raise ValueError(f"No case with id {case_id}")
        if feeling not in FEELINGS:
            raise ValueError(f"feeling must be one of {FEELINGS}")
        score = max(1, min(10, int(score)))
        lang = case["language"]
        history = self.db.checkins(case_id)
        start = date.fromisoformat(case["start_day"])
        day_no = (today - start).days + 1
        already_today = any(h["day"] == today.isoformat() for h in history)

        # --- quests and XP (only the first check-in of a day earns XP) ---
        valid_ids = {q["id"]: q for q in case["quests"]}
        done = [qid for qid in (quests_done or []) if qid in valid_ids]
        xp = 0
        if not already_today:
            xp += XP_CHECKIN + XP_QUEST * len(done)
            if feeling == "better":
                xp += XP_BETTER
            if valid_ids and len(done) == len(valid_ids):
                xp += XP_ALL_QUESTS
        days = sorted({date.fromisoformat(h["day"]) for h in history} | {today})
        streak = streak_on(days, today)
        if not already_today and streak > 0 and streak % 3 == 0:
            xp += XP_STREAK_BONUS

        counts = dict(case["quest_counts"])
        if not already_today:
            for qid in done:
                kind = valid_ids[qid]["kind"]
                counts[kind] = counts.get(kind, 0) + 1

        # --- badges ---
        earned = list(case["badges"])
        new = []

        def award(key):
            if key not in earned:
                earned.append(key)
                new.append(key)

        award("first_step")
        if streak >= 3:
            award("streak_3")
        if streak >= 7:
            award("streak_7")
        if valid_ids and len(done) == len(valid_ids):
            award("quest_champion")
        if counts.get("water", 0) >= 3:
            award("hydration_hero")
        if counts.get("rest", 0) >= 3:
            award("rest_master")
        if feeling == "worse":
            award("honest_heart")
        if feeling == "better" and history and history[-1]["feeling"] == "worse":
            award("comeback")
        recovered = feeling == "better" and score <= 2
        if recovered:
            award("recovered")

        # --- does triage need to run again? ---
        prev_score = history[-1]["score"] if history else case["first_score"]
        not_improving_days = day_no > REVIEW_AFTER_DAYS.get(case["level"], 3) and feeling != "better"
        review = feeling == "worse" or score >= prev_score + 2 or not_improving_days
        new_triage = None
        level, specialty = case["level"], case["specialty"]
        if review and not recovered:
            text = (f"Follow-up on recovery day {day_no}. Original problem: {case['condition']}. "
                    f"Symptom score went from {case['first_score']}/10 on day 1 to {score}/10 today. "
                    f"Patient feels {feeling} compared to yesterday. Patient's note: {note or 'none'}")
            try:
                new_triage = triage(self.llm, text=text, profile=case["profile"], language=lang)
                if new_triage.get("valid"):
                    level = new_triage["level"]
                    specialty = new_triage.get("specialty") or specialty
            except Exception:  # noqa: BLE001 - keep the check-in working if the API fails
                new_triage = None

        # --- personalised message + tomorrow's quests from the LLM ---
        total_xp = case["xp"] + xp
        plant = plant_for(total_xp, lang)
        message, quests = self._generate(case, lang, day_no, feeling, score, streak, plant, note, today)

        self.db.update_case(case_id, xp=total_xp, badges=earned, quests=quests, quest_counts=counts,
                            level=level, specialty=specialty,
                            status="recovered" if recovered else case["status"])
        self.db.add_checkin(case_id, day=today.isoformat(), feeling=feeling, score=score, note=note,
                            quests_done=done, xp_gained=xp, level=level, message=message)

        return {
            "case_id": case_id, "day": day_no, "feeling": feeling, "score": score,
            "xp_gained": xp, "xp_total": total_xp, "streak": streak, "plant": plant,
            "new_badges": [badge_info(k) for k in new],
            "badges": [badge_info(k) for k in earned],
            "message": message, "tomorrow_quests": quests,
            "already_checked_in_today": already_today,
            "recovered": recovered,
            "retriaged": new_triage is not None and new_triage.get("valid", False),
            "level": level, "level_changed": level != case["level"], "specialty": specialty,
            "see_doctor": level in ("yellow", "orange", "red") and (review or level != case["level"]),
            "triage": new_triage,
        }

    def _generate(self, case, lang, day_no, feeling, score, streak, plant, note, today):
        prompt = CHECKIN_PROMPT.format(
            condition=case["condition"] or "unknown", level=case["level"], day=day_no, feeling=feeling,
            score=score, first=case["first_score"], streak=streak, plant=plant["name"],
            note=note or "none", language=LANG_NAME.get(lang, "English"))
        try:
            out = self.llm.chat_json(prompt, [{"role": "user", "content": "Write today's check-in reply."}],
                                     temperature=0.7)
            message = str(out.get("message") or "").strip()
            quests = make_quests(out.get("quests") or [], today)
        except Exception:  # noqa: BLE001 - the game still works without the LLM
            message, quests = "", []
        if not message:
            message = FALLBACK_MESSAGE[feeling].get(lang, FALLBACK_MESSAGE[feeling]["en"])
        if len(quests) < 3:
            quests = make_quests(DEFAULT_QUESTS.get(lang, DEFAULT_QUESTS["en"]), today)
        return message, quests

    # ----- everything the screen needs to draw the journey -------------------
    def journey(self, case_id: int, today: date | None = None) -> dict:
        today = today or date.today()
        case = self.db.get_case(case_id)
        if case is None:
            raise ValueError(f"No case with id {case_id}")
        history = self.db.checkins(case_id)
        days = sorted({date.fromisoformat(h["day"]) for h in history})
        streak = streak_on(days, today) or (streak_on(days, date.fromordinal(today.toordinal() - 1)) if days else 0)
        scores = [case["first_score"]] + [h["score"] for h in history]
        first, last = scores[0], scores[-1]
        progress = 0.0 if first <= 1 else max(0.0, min(1.0, (first - last) / (first - 1)))
        return {
            "case_id": case_id, "condition": case["condition"], "level": case["level"],
            "specialty": case["specialty"], "status": case["status"], "language": case["language"],
            "day": (today - date.fromisoformat(case["start_day"])).days + 1,
            "streak": streak, "checked_in_today": today in days,
            "xp": case["xp"], "plant": plant_for(case["xp"], case["language"]),
            "recovery_progress": progress, "scores": scores,
            "badges": [badge_info(k) for k in case["badges"]],
            "locked_badges": [badge_info(k) for k in BADGES if k not in case["badges"]],
            "today_quests": case["quests"],
            "history": [{"day": h["day"], "feeling": h["feeling"], "score": h["score"],
                         "xp": h["xp_gained"], "level": h["level"]} for h in history],
        }
