"""Check-in game tests with a fake LLM and an in-memory database."""
from datetime import date, timedelta

from app.checkin import XP_CHECKIN, CheckinGame, plant_for, streak_on
from app.db import DB

D1 = date(2026, 11, 20)


class FakeLLM:
    """Answers check-in prompts with quests, triage prompts with a level."""
    def __init__(self, triage_level="orange", fail=False):
        self.triage_level = triage_level
        self.fail = fail
        self.triage_calls = 0

    def chat_json(self, system, messages, temperature=0.0):
        if self.fail:
            raise RuntimeError("API down")
        if "triage nurse" in system:
            self.triage_calls += 1
            return {"level": self.triage_level, "specialty": "ENT Specialist",
                    "condition": "throat infection", "reason": "worse", "advice": "See a doctor today."}
        return {"message": "Well done, keep going!",
                "quests": [{"title": "Warm salt-water gargle", "emoji": "🧂", "kind": "care"},
                           {"title": "Drink 8 glasses of water", "emoji": "💧", "kind": "water"},
                           {"title": "Nap after lunch", "emoji": "😴", "kind": "rest"}]}


def new_game(**kw):
    game = CheckinGame(DB(":memory:"), FakeLLM(**kw))
    case_id = game.start_case({"level": "green", "specialty": "General Physician", "condition": "sore throat"},
                              {"severity_score": 6}, "en", today=D1)
    return game, case_id


def all_quests(game, case_id):
    return [q["id"] for q in game.db.get_case(case_id)["quests"]]


def test_first_checkin_gives_xp_badge_and_new_quests():
    game, cid = new_game()
    r = game.check_in(cid, "same", 6, [], today=D1)
    assert r["xp_gained"] == XP_CHECKIN
    assert [b["key"] for b in r["new_badges"]] == ["first_step"]
    assert r["streak"] == 1 and r["day"] == 1
    assert len(r["tomorrow_quests"]) == 3 and r["tomorrow_quests"][0]["title"] == "Warm salt-water gargle"
    assert r["retriaged"] is False


def test_streak_quests_and_plant_growth():
    game, cid = new_game()
    game.check_in(cid, "same", 6, all_quests(game, cid), today=D1)
    game.check_in(cid, "better", 4, all_quests(game, cid), today=D1 + timedelta(days=1))
    r = game.check_in(cid, "better", 3, all_quests(game, cid), today=D1 + timedelta(days=2))
    assert r["streak"] == 3
    keys = {b["key"] for b in r["badges"]}
    assert {"first_step", "quest_champion", "streak_3"} <= keys
    # day 3: 10 checkin + 10 better + 15 quests + 10 all-quests + 15 streak bonus
    assert r["xp_gained"] == 60
    assert r["plant"]["stage"] >= 2


def test_same_day_twice_gives_no_extra_xp():
    game, cid = new_game()
    game.check_in(cid, "same", 6, [], today=D1)
    r = game.check_in(cid, "same", 6, [], today=D1)
    assert r["already_checked_in_today"] and r["xp_gained"] == 0


def test_feeling_worse_runs_triage_again():
    game, cid = new_game(triage_level="orange")
    game.check_in(cid, "same", 6, [], today=D1)
    r = game.check_in(cid, "worse", 8, [], note="now fever too", today=D1 + timedelta(days=1))
    assert r["retriaged"] and r["level"] == "orange" and r["level_changed"]
    assert r["see_doctor"] and r["specialty"] == "ENT Specialist"
    assert "honest_heart" in {b["key"] for b in r["new_badges"]}
    assert game.db.get_case(cid)["level"] == "orange"


def test_not_improving_for_too_long_runs_triage():
    game, cid = new_game(triage_level="yellow")
    for d in range(4):  # green cases are reviewed after 3 days without improvement
        r = game.check_in(cid, "same", 6, [], today=D1 + timedelta(days=d))
    assert r["retriaged"] and r["level"] == "yellow"


def test_recovery_and_comeback():
    game, cid = new_game()
    game.check_in(cid, "worse", 7, [], today=D1)
    r = game.check_in(cid, "better", 2, [], today=D1 + timedelta(days=1))
    keys = {b["key"] for b in r["new_badges"]}
    assert {"comeback", "recovered"} <= keys
    assert r["recovered"] and game.db.get_case(cid)["status"] == "recovered"


def test_works_when_llm_is_down():
    game, cid = new_game(fail=True)
    r = game.check_in(cid, "worse", 9, [], today=D1)
    assert r["message"]  # fallback message
    assert len(r["tomorrow_quests"]) == 3
    assert r["retriaged"] is False


def test_journey_for_the_screen():
    game, cid = new_game()
    game.check_in(cid, "better", 4, [], today=D1)
    j = game.journey(cid, today=D1)
    assert j["scores"] == [6, 4]
    assert abs(j["recovery_progress"] - 0.4) < 1e-9
    assert j["checked_in_today"] and j["streak"] == 1
    assert len(j["badges"]) + len(j["locked_badges"]) == 9


def test_helpers():
    assert plant_for(0)["key"] == "seed" and plant_for(250)["key"] == "flowering"
    assert plant_for(80, "mr")["name"] == "छोटी तुळस"
    days = [D1, D1 + timedelta(days=1), D1 + timedelta(days=3)]
    assert streak_on(days, D1 + timedelta(days=3)) == 1
    assert streak_on(days, D1 + timedelta(days=1)) == 2
