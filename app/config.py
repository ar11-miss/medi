import os
from pathlib import Path

from dotenv import load_dotenv

# Always read the .env next to the project, whichever folder you run from.
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
if not ENV_FILE.exists() and (ROOT / ".env.txt").exists():
    ENV_FILE = ROOT / ".env.txt"  # Windows Notepad often saves it as .env.txt
# utf-8-sig also reads files that Notepad saved "with BOM"
load_dotenv(ENV_FILE, encoding="utf-8-sig")

GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip().strip('"').strip("'") or None
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Faster model for chat questions, home care and check-in messages (triage keeps GROQ_MODEL)
GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
# GPT-OSS models "think" before answering; low = much faster replies (low | medium | high)
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY") or None
# Free doctor search, no card: https://myprojects.geoapify.com
GEOAPIFY_API_KEY = (os.getenv("GEOAPIFY_API_KEY") or "").strip() or None
