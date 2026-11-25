"""MediAid diagnosis: tests your .env, internet, Groq and the map servers.
Run:  python diagnose.py      (or double-click diagnose.bat)
Then send the whole output (or a screenshot) to get help."""
import os
import sys
import time
import traceback

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = []


def line(tag, msg):
    print(f"{tag} {msg}")
    if tag == BAD:
        problems.append(msg)


print("=" * 60)
print(" MediAid diagnosis")
print("=" * 60)
print(f"Python {sys.version.split()[0]} at {sys.executable}")
print(f"Folder: {os.getcwd()}")

# ---------------------------------------------------------------- 1. files
print("\n--- 1. Project files and .env ---")
for f in ("app/api.py", "app/llm.py", "frontend/dist/index.html", ".env"):
    line(OK if os.path.exists(f) else BAD, f"{f} {'found' if os.path.exists(f) else 'MISSING'}")

try:
    from dotenv import dotenv_values
    env = dotenv_values(".env") if os.path.exists(".env") else {}
except Exception as e:  # noqa: BLE001
    env = {}
    line(BAD, f"python-dotenv not installed ({e}). Run: python -m pip install -r requirements.txt")

from app import config  # noqa: E402

key = config.GROQ_API_KEY or ""
if not key:
    line(BAD, "GROQ_API_KEY is empty. Put your key in .env")
elif "your_key" in key:
    line(BAD, "GROQ_API_KEY is still the example placeholder")
else:
    line(OK, f"GROQ_API_KEY loaded: {key[:6]}...{key[-4:]} ({len(key)} characters)")
    if key != key.strip() or key.startswith(("'", '"')):
        line(BAD, "GROQ_API_KEY has spaces or quotes around it. Remove them in .env")
line(OK if config.GEOAPIFY_API_KEY else WARN,
     "GEOAPIFY_API_KEY " + ("loaded" if config.GEOAPIFY_API_KEY else "missing: doctor list will be limited. Free key: https://myprojects.geoapify.com"))
for name in ("GROQ_MODEL", "GROQ_FAST_MODEL", "GROQ_REASONING_EFFORT"):
    val = getattr(config, name)
    src = "from .env" if name in env else "DEFAULT (line missing in .env)"
    line(OK if name in env else WARN, f"{name} = {val}   [{src}]")
if os.environ.get("GROQ_MODEL") and os.environ.get("GROQ_MODEL") != env.get("GROQ_MODEL"):
    line(WARN, f"A Windows environment variable GROQ_MODEL={os.environ['GROQ_MODEL']} overrides .env")
for p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    if os.environ.get(p):
        line(WARN, f"Proxy set: {p}={os.environ[p]}")

# ---------------------------------------------------------------- 2. internet
print("\n--- 2. Internet ---")
import requests  # noqa: E402

sites = {
    "Groq API": "https://api.groq.com",
    "Geoapify (doctor search)": "https://api.geoapify.com",
    "OpenStreetMap search": "https://nominatim.openstreetmap.org/status",
    "Google": "https://www.google.com",
}
for label, url in sites.items():
    try:
        t0 = time.time()
        r = requests.get(url, timeout=15)
        line(OK, f"{label}: reachable (HTTP {r.status_code}, {time.time() - t0:.1f}s)")
    except requests.exceptions.SSLError as e:
        line(BAD, f"{label}: SSL error. Your network (college/office WiFi or antivirus) is intercepting HTTPS. {str(e)[:120]}")
    except requests.exceptions.ProxyError as e:
        line(BAD, f"{label}: proxy blocked it. {str(e)[:120]}")
    except requests.exceptions.ConnectionError as e:
        line(BAD, f"{label}: cannot connect (blocked by WiFi/firewall, or no internet). {str(e)[:120]}")
    except requests.exceptions.Timeout:
        line(BAD, f"{label}: timed out")

# ---------------------------------------------------------------- 3. Groq
print("\n--- 3. Groq ---")
if key and "your_key" not in key:
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers={"Authorization": f"Bearer {key.strip()}"}, timeout=20)
        if r.status_code == 401:
            line(BAD, "Groq says the API key is INVALID (401). Make a new key at console.groq.com/keys")
        elif r.ok:
            ids = sorted(m["id"] for m in r.json().get("data", []))
            line(OK, f"Key works. Your account can use {len(ids)} models.")
            for m in dict.fromkeys([config.GROQ_MODEL, config.GROQ_FAST_MODEL]):
                line(OK if m in ids else BAD, f"Model '{m}' {'available' if m in ids else 'NOT available to your account'}")
            print("      Models you can use:", ", ".join(i for i in ids if "whisper" not in i and "tts" not in i))
        else:
            line(BAD, f"Groq model list failed: HTTP {r.status_code} {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        line(BAD, f"Could not ask Groq for the model list: {e.__class__.__name__}: {str(e)[:150]}")

    try:
        import groq
        print(f"      groq package version: {groq.__version__}")
        from app.llm import GroqLLM
        for model in dict.fromkeys([config.GROQ_MODEL, config.GROQ_FAST_MODEL]):
            llm = GroqLLM(model=model)
            for label, kwargs in (("plain text", {}),
                                  ("JSON mode", {"response_format": {"type": "json_object"}})):
                try:
                    t0 = time.time()
                    resp = llm._create(model=model, messages=[
                        {"role": "system", "content": "Reply in JSON with key 'ok' set to true."},
                        {"role": "user", "content": "ping"}], **kwargs)
                    content = (resp.choices[0].message.content or "").strip()
                    finish = resp.choices[0].finish_reason
                    if not content:
                        line(BAD, f"{model} {label}: EMPTY reply (finish_reason={finish})")
                    else:
                        line(OK, f"{model} {label}: {time.time() - t0:.1f}s -> {content[:80]!r}")
                except Exception as e:  # noqa: BLE001
                    line(BAD, f"{model} {label}: {e.__class__.__name__}: {str(e)[:200]}")
            print(f"      reasoning_effort={config.GROQ_REASONING_EFFORT} used: {llm._effort_ok}")
    except Exception:  # noqa: BLE001
        line(BAD, "Groq test crashed:\n" + traceback.format_exc()[-600:])

    # a real MediAid step
    try:
        from app.intake import IntakeSession
        from app.llm import GroqLLM
        t0 = time.time()
        r = IntakeSession(GroqLLM(model=config.GROQ_FAST_MODEL)).step("I have a sore throat since yesterday")
        line(OK, f"Intake step works ({time.time() - t0:.1f}s). Next question: {r['question']!r}")
        print(f"      profile so far: {r['profile']['symptoms']}, duration={r['profile']['duration_days']}")
    except Exception as e:  # noqa: BLE001
        line(BAD, f"Intake step failed: {e.__class__.__name__}: {str(e)[:200]}")
else:
    line(BAD, "Skipping Groq tests: no valid key")

# ---------------------------------------------------------------- 4. doctors
print("\n--- 4. Doctor finder (near Alandi) ---")
try:
    from app.doctors import find_doctors
    t0 = time.time()
    res = find_doctors("yellow", "General Physician", 18.6770, 73.8970)
    n = len(res["clinics"])
    line(OK if n else BAD, f"Found {n} clinics via {res['source']} ({time.time() - t0:.1f}s)")
    if res["note"]:
        print("      note:", res["note"])
    for c in res["clinics"][:3]:
        print(f"      - {c['name']} ({c['distance_km']} km)")
except Exception:  # noqa: BLE001
    line(BAD, "Doctor finder crashed:\n" + traceback.format_exc()[-600:])

# ---------------------------------------------------------------- summary
print("\n" + "=" * 60)
if problems:
    print(f" {len(problems)} problem(s) found:")
    for p in problems:
        print("  -", p.splitlines()[0])
else:
    print(" Everything works. If the app still fails, restart run_mediaid.bat")
    print(" (an old copy of the server may still be running).")
print("=" * 60)
print("Send this whole output (or a screenshot) to get help.")
