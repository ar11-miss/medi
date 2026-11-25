"""Chat with the intake nurse in your terminal:  python try_intake.py"""
import json

from app.intake import IntakeSession
from app.llm import GroqLLM

session = IntakeSession(GroqLLM())
print("MediAid: Hello! Tell me what's bothering you. (type 'quit' to stop)\n")

while not session.done:
    text = input("You: ").strip()
    if text.lower() == "quit":
        break
    if not text:
        continue
    result = session.step(text)
    if result["question"]:
        print(f"MediAid: {result['question']}\n")

print("\nCollected profile:")
print(json.dumps(session.profile, ensure_ascii=False, indent=2))
