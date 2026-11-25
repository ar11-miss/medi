# MediAid

Nurse-like symptom assistant (English, Hindi, Marathi) using a Groq-hosted LLM.
Built for the Generative AI subject.

## Setup

Windows:
```
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Mac:
```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Put your Groq key (from https://console.groq.com/keys) in `.env`, and make sure
the model line says `GROQ_MODEL=openai/gpt-oss-120b`. Then:

```
python check_groq.py      # confirms the key and model work
python -m pytest -q       # runs the tests (no key needed): 39 passed
python try_intake.py      # chat with the intake nurse
python try_triage.py      # intake + severity level + which doctor + home care (RAG)
python try_checkin.py new # I feel unwell: report symptoms and plant your Tulsi
python try_checkin.py     # today's check-in game   (add --day 2, --day 3 ... to demo)
python try_checkin.py status   # plant, streak, badges, recovery progress
python try_doctors.py     # doctors near you for your latest case
```

## Run the app (web UI)

**Windows, easiest:** double-click `run_mediaid.bat`. It installs packages, checks your Groq key
and model, starts MediAid and opens http://localhost:8000. Close its window to stop.

Or by hand:

The built UI is already in `frontend/dist`, so you only need Python:

```
python -m uvicorn app.api:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

**Changing the UI:** install Node.js 18+ once, then in a second terminal:

```
cd frontend
npm install
npm run dev          # live-reloading UI at http://localhost:5173 (keep the Python server running)
npm run build        # when done: updates frontend/dist, which the Python server serves
```

| Screen | What it does |
| --- | --- |
| Dashboard | Tulsi XP, "Feeling unwell?", latest result (severity, home care, doctor), badges, recovery chart |
| Check Symptoms | Nurse chat in English/Hindi/Marathi, then severity, specialist, RAG home care |
| Daily Check-in | Better/same/worse, symptom slider, quests, XP reward, plant, streak, badges |
| Find Doctors | Your location, specialty and distance, nearby clinics with Call and Directions |
| Settings / Support | Your name, Groq connection status, emergency numbers |

## Speed

GPT-OSS models "think" before answering. `.env` sets `GROQ_REASONING_EFFORT=low`
for fast replies, and uses the smaller `GROQ_FAST_MODEL` (GPT-OSS 20B) for the chat
questions and home care, while the severity decision uses `GROQ_MODEL` (GPT-OSS 120B).

## Doctor finder

1. Get a free key at https://myprojects.geoapify.com (no card, 3000 searches a day).
2. Add `GEOAPIFY_API_KEY=your_key` to `.env`.

MediAid searches Google Places (if you have that key), then Geoapify, then
OpenStreetMap. The page always also shows a Google map of the same search, so
users can see nearby doctors even if every list source fails. Run
`python check_doctors.py` to test it.

## Deploy on Render

1. Push this folder to a GitHub repo (`.env` is ignored, so your key stays private).
2. On https://render.com: **New → Blueprint**, pick the repo. It reads `render.yaml`.
3. Paste your `GROQ_API_KEY` when asked, then deploy. You get a public link.

Run `npm run build` and push again whenever you change the UI. On the free plan the
SQLite database resets when the service restarts, which is fine for a demo.

## Accuracy report (for the research paper)

```
python evaluate.py --limit 5        # quick check: 5 cases, about 1 minute
python evaluate.py                  # all 60 cases with the model in .env
python evaluate.py --models openai/gpt-oss-120b,openai/gpt-oss-20b    # compare two models
```

Results go in the `results` folder:

| File | What it is |
| --- | --- |
| `report_<model>.md` | All metrics as tables, ready to copy into the paper |
| `confusion_<model>.png` | Confusion-matrix figure for the paper |
| `predictions_<model>.csv` | Every case: correct answer vs model answer (open in Excel) |
| `comparison.md` | Side-by-side table when you test 2+ models |

For the RAG module:

```
python evaluate_rag.py                     # retrieval only, no key needed
python evaluate_rag.py --llm --generate    # + Groq re-ranking and full answers
```

This writes `results/rag_report.md`: top-1 accuracy, top-3 recall, MRR, Groq
re-ranking accuracy, how often it correctly says "no match", and how many answers
contained a made-up medicine (caught by the grounding check). The 42 test queries
are in `data/rag_test.csv`.

Triage metrics: accuracy, within-one-level accuracy, precision/recall/F1 per level and
macro, under-triage rate, over-triage rate, emergency recall, severe
under-triage, specialist accuracy, accuracy per language, response time.

**About the test set (`data/test_cases.csv`):** 60 cases, 20 each in English,
Hindi and Marathi, 5 per severity level per language. The correct answers were
drafted for this project; have a doctor or your guide check them before you
report results, and say so in the paper.

## Build status

| Step | Module | Status |
| --- | --- | --- |
| 1 | Setup, Groq client (`app/llm.py`) | Done |
| 2 | Intake: follow-up questions + patient profile (`app/intake.py`) | Done |
| 3 | Triage: severity level + specialist (`app/triage.py`) | Done |
| 3b | Accuracy evaluation (`evaluate.py`, `app/metrics.py`) | Done |
| 4 | Daily check-in game "Grow your Tulsi" (`app/checkin.py`, `app/db.py`) | Done |
| 5 | Doctor finder from triage result (`app/doctors.py`) | Done |
| 6 | Remedies with RAG + Groq (`app/rag.py`, `data/remedies_kb.json`) | Done |
| 7 | Web UI: React (`frontend/`) + FastAPI (`app/api.py`) | Done |

## Remedies with RAG

Used for green and yellow cases (orange and red go straight to a doctor).

1. **Retrieve:** finds the 3 closest entries in `data/remedies_kb.json` (12 common minor
   problems) using TF-IDF over character n-grams, which works for English, Hindi and Marathi.
   If you install `requirements-embeddings.txt`, it also uses multilingual embeddings
   and combines both rankings (hybrid search).
2. **Re-rank:** Groq reads the 3 candidates and picks the one that matches, or says "none".
3. **Personalise:** removes medicines this patient shouldn't take, based on age, pregnancy,
   allergies, illnesses and medicines they already take. Children get home care only, plus
   a note to ask a pharmacist for the dose.
4. **Generate:** Groq writes the answer in the patient's language from that entry only.
5. **Grounding check:** any medicine Groq names that isn't in the entry is dropped and counted.

Each knowledge-base entry has home care, simple OTC medicines with adult doses, who
should avoid each medicine, and when to see a doctor. Have a doctor or pharmacist
review `data/remedies_kb.json` before real use.

## Daily check-in game: "Grow your Tulsi"

Every day the patient answers 3 quick things: better / same / worse, a symptom
score from 1 to 10, and which of yesterday's 3 quests they finished.

| Earns XP | XP |
| --- | --- |
| Checking in | +10 |
| Feeling better | +10 |
| Each quest finished | +5 |
| All 3 quests finished | +10 bonus |
| Every 3rd day in a row | +15 streak bonus |

- **Tulsi plant** grows with XP: seed → sprout (30) → young (80) → bushy (150) → flowering (250).
- **9 badges:** First Step, On Fire (3-day streak), Week Warrior (7 days), Quest Champion,
  Hydration Hero, Rest Master, Honest Heart (told us when worse), Comeback, Recovered!
- **Quests are written by the LLM** for the patient's illness and language (e.g. salt-water gargle for
  a sore throat), plus a short encouraging message.
- **Triage runs again** if the patient feels worse, the score jumps by 2+, or there's no improvement
  after a few days (3 for green, 5 for yellow). If the new level needs a doctor, the doctor finder is next.
- Data is saved in `mediaid.db` (SQLite) in the folder you run from.

## Doctor finder

Takes the triage level + specialty and the user's location. Red always shows the
nearest hospitals and 108/112. Sources: Google Places (optional) → Geoapify (free key)
→ OpenStreetMap, plus an embedded Google map. If no clinic is listed under the
specialty nearby, it shows the nearest clinics and hospitals instead.

## GenAI concepts used so far

- **Role prompting:** the system prompt makes the model act as a nurse.
- **Conversation memory:** the full chat is sent on every turn.
- **Structured output:** the model replies in a fixed JSON format (Groq JSON mode).
- **Zero-shot classification:** the LLM sorts cases into 4 levels with no training, only instructions.
- **Multilingual generation:** it replies in the user's language and script.
- **Personalised generation:** daily quests and messages written for each patient.
- **Context injection:** streak, scores and history are put into the prompt.
- **LLM + external tools:** triage output drives a map search for doctors.
- **RAG:** retrieval from a knowledge base, LLM re-ranking, grounded generation.
- **Hallucination check:** medicines not in the retrieved entry are dropped.
