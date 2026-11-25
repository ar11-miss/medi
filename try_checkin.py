"""Play the daily check-in game in the terminal.

  python try_checkin.py new          I feel unwell: report new symptoms (asks questions, runs triage)
  python try_checkin.py              do today's check-in
  python try_checkin.py --day 3      pretend it is day 3 (for demos)
  python try_checkin.py status       see your journey, plant and badges
"""
import argparse
from datetime import date, timedelta

from app.checkin import CheckinGame
from app.db import DB
from app.intake import IntakeSession
from app.llm import GroqLLM
from app.triage import triage

LEVEL_EMOJI = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}


def bar(fraction: float, width: int = 20) -> str:
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return "█" * filled + "░" * (width - filled)


def show_journey(j: dict) -> None:
    p = j["plant"]
    print(f"\n{p['emoji']}  Your Tulsi: {p['name']}   XP {j['xp']}"
          + (f" / {p['next_stage_xp']}" if p["next_stage_xp"] else " (fully grown!)"))
    print(f"   Growth   [{bar(p['progress'])}]")
    print(f"   Recovery [{bar(j['recovery_progress'])}] {round(100 * j['recovery_progress'])}%")
    print(f"🔥 Streak: {j['streak']} day(s)    Day {j['day']} of recovery    "
          f"{LEVEL_EMOJI.get(j['level'], '')} {j['level']}  ({j['condition']})")
    print("   Symptom scores: " + " → ".join(str(s) for s in j["scores"]))
    got = " ".join(f"{b['emoji']} {b['name']}" for b in j["badges"]) or "none yet"
    print(f"🏅 Badges: {got}")
    print(f"🔒 Locked: {', '.join(b['name'] for b in j['locked_badges'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="checkin", choices=["new", "checkin", "status"])
    ap.add_argument("--day", type=int, help="pretend today is this recovery day (demo)")
    args = ap.parse_args()

    db = DB()
    llm = GroqLLM()
    game = CheckinGame(db, llm)

    if args.action == "new":
        session = IntakeSession(llm)
        print("MediAid: Tell me what's bothering you.\n")
        first = None
        while not session.done:
            text = input("You: ").strip()
            if not text:
                continue
            first = first or text
            r = session.step(text)
            if r["question"]:
                print(f"MediAid: {r['question']}\n")
        t = triage(llm, text=first, profile=session.profile, language=session.language)
        case_id = game.start_case(t, session.profile, session.language)
        print(f"\n{LEVEL_EMOJI.get(t['level'], '')} {str(t['level']).upper()}: {t['meaning']}")
        print(f"See: {t['specialty']}   Likely: {t['condition']}\n{t['advice']}")
        print(f"\n🌰 Your Tulsi seed is planted! Check in every day to help it grow. (case #{case_id})")
        print("Today's quests:")
        for q in db.get_case(case_id)["quests"]:
            print(f"   {q['emoji']} {q['title']}")
        return

    case = db.latest_case()
    if case is None:
        print("No symptoms reported yet. Run:  python try_checkin.py new")
        return
    start = date.fromisoformat(case["start_day"])
    today = start + timedelta(days=args.day - 1) if args.day else date.today()

    if args.action == "status":
        show_journey(game.journey(case["id"], today))
        return

    print(f"\n☀️  Day {(today - start).days + 1} check-in for: {case['condition']}")
    feeling = ""
    while feeling not in ("better", "same", "worse"):
        feeling = {"1": "better", "2": "same", "3": "worse"}.get(
            input("How do you feel compared to yesterday?  1) better  2) same  3) worse : ").strip(), "")
    score = 0
    while not 1 <= score <= 10:
        try:
            score = int(input("How bad are your symptoms now, 1 (none) to 10 (worst)? ").strip())
        except ValueError:
            pass
    done = []
    print("Which quests did you finish? (y/n)")
    for q in case["quests"]:
        if input(f"   {q['emoji']} {q['title']}? ").strip().lower().startswith("y"):
            done.append(q["id"])
    note = input("Anything else to tell MediAid? (Enter to skip) ").strip()

    r = game.check_in(case["id"], feeling, score, done, note, today)
    print("\n" + "─" * 50)
    if r["already_checked_in_today"]:
        print("You already checked in today, so no new XP. Come back tomorrow!")
    else:
        print(f"✨ +{r['xp_gained']} XP   (total {r['xp_total']})   🔥 streak {r['streak']}")
    for b in r["new_badges"]:
        print(f"🏅 NEW BADGE: {b['emoji']} {b['name']}: {b['description']}")
    print(f"{r['plant']['emoji']}  Tulsi stage: {r['plant']['name']}")
    print(f"\nMediAid: {r['message']}")
    if r["recovered"]:
        print("\n🎉 You've recovered! Your Tulsi is proud of you.")
    if r["retriaged"]:
        t = r["triage"]
        print(f"\nI checked your symptoms again: {LEVEL_EMOJI.get(r['level'], '')} {r['level'].upper()}. "
              f"{t['meaning']}\nSee: {r['specialty']}. {t['advice']}")
        if r["see_doctor"]:
            print("Run  python try_doctors.py  to find doctors near you.")
    print("\nTomorrow's quests:")
    for q in r["tomorrow_quests"]:
        print(f"   {q['emoji']} {q['title']}")


if __name__ == "__main__":
    main()
