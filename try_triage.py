"""Intake + triage + remedies (RAG) in the terminal:  python try_triage.py"""
from app.intake import IntakeSession
from app.llm import GroqLLM
from app.rag import RemedyRAG
from app.triage import triage

llm = GroqLLM()
session = IntakeSession(llm)
print("MediAid: Hello! Tell me what's bothering you. (type 'quit' to stop)\n")

first_message = None
while not session.done:
    text = input("You: ").strip()
    if text.lower() == "quit":
        raise SystemExit
    if not text:
        continue
    first_message = first_message or text
    result = session.step(text)
    if result["question"]:
        print(f"MediAid: {result['question']}\n")

t = triage(llm, text=first_message, profile=session.profile, language=session.language)
print("\n----- MediAid result -----")
print(f"Severity : {str(t['level']).upper()}  ({t['meaning']})")
print(f"See      : {t['specialty']}")
print(f"Likely   : {t['condition']}")
print(f"Why      : {t['reason']}")
print(f"Advice   : {t['advice']}")

if t["level"] in ("green", "yellow"):
    print("\nLooking up home care in the MediAid knowledge base...")
    r = RemedyRAG(llm).get_remedies(text=first_message, profile=session.profile, triage=t,
                                    language=session.language)
    if not r["matched"]:
        print(r["summary"])
    else:
        print(f"\n📚 {r['source']}  (match confidence {r['confidence']:.2f})")
        print(f"\n{r['summary']}")
        print("\n🏠 Home care:")
        for h in r["home_care"]:
            print(f"   • {h}")
        if r["medicines"]:
            print("\n💊 Medicines you can take (follow the pack label):")
            for m in r["medicines"]:
                print(f"   • {m['name']}: {m['how_to_take']}" + (f"  ({m['note']})" if m["note"] else ""))
        for x in r["excluded_medicines"]:
            print(f"   ✗ {x['name']} left out: {x['reason']}")
        for n in r["notes"]:
            print(f"   ℹ️  {n}")
        print("\n🩺 See a doctor if:")
        for s in r["see_doctor_if"]:
            print(f"   • {s}")
else:
    print("\nNo home remedies for this level. Run  python try_doctors.py  to find a doctor near you.")
