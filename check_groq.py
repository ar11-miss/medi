"""Run this once to confirm your Groq key works:  python check_groq.py"""
import time

from app import config
from app.llm import GroqLLM

for model in dict.fromkeys([config.GROQ_MODEL, config.GROQ_FAST_MODEL]):
    t0 = time.time()
    reply = GroqLLM(model=model).chat_json(
        "You are a test. Reply in JSON with key 'ok' set to true.",
        [{"role": "user", "content": "ping"}],
    )
    print(f"Groq is working: {model}  ({time.time() - t0:.1f} s)  {reply}")
