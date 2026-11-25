"""Accuracy report for MediAid triage.

Runs every case in data/test_cases.csv through the Groq model and writes:
  results/predictions_<model>.csv   every case with gold vs predicted answer
  results/report_<model>.md         all metrics, as tables ready for the paper
  results/confusion_<model>.png     confusion-matrix image
  results/comparison.md             side-by-side table (when you test 2+ models)

Usage:
  python evaluate.py --limit 5                       # quick check on 5 cases
  python evaluate.py                                 # full run, model from .env
  python evaluate.py --models openai/gpt-oss-120b,openai/gpt-oss-20b
"""
import argparse
import csv
import json
import os
import re
import time
from datetime import datetime

from app import config
from app.metrics import summarise
from app.triage import LEVELS, triage

LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


def load_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def call_with_retry(fn, tries: int = 4):
    """Retry on network errors and rate limits; give up after `tries` attempts."""
    for attempt in range(1, tries + 1):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001 - any API/parse error counts as a failed attempt
            msg = str(e)
            if attempt == tries:
                return None, msg
            wait = 30 if ("429" in msg or "rate" in msg.lower()) else 3 * attempt
            print(f"    retry {attempt}/{tries - 1} in {wait}s: {msg[:100]}")
            time.sleep(wait)


def run_model(llm, model: str, cases: list[dict], delay: float) -> list[dict]:
    rows = []
    for i, c in enumerate(cases, 1):
        t0 = time.time()
        result, error = call_with_retry(lambda: triage(llm, text=c["text"]))
        latency = round(time.time() - t0, 2)
        result = result or {}
        row = {
            "id": c["id"], "language": c["language"], "text": c["text"],
            "gold_level": c["gold_level"], "pred_level": result.get("level") or "invalid",
            "gold_specialty": c["gold_specialty"], "pred_specialty": result.get("specialty") or "",
            "condition": result.get("condition") or "", "reason": result.get("reason") or "",
            "latency_s": latency if not error else None, "error": error or "",
        }
        rows.append(row)
        mark = "OK  " if row["pred_level"] == row["gold_level"] else "MISS"
        print(f"  [{i:>2}/{len(cases)}] {c['id']} {mark} gold={row['gold_level']:<6} "
              f"pred={row['pred_level']:<7} specialty={row['pred_specialty']}")
        time.sleep(delay)
    return rows


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def write_report(model: str, s: dict, path: str, dataset: str) -> None:
    L = []
    L.append(f"# MediAid triage accuracy report: `{model}`\n")
    L.append(f"Run on {datetime.now():%Y-%m-%d %H:%M}, dataset `{dataset}`, {s['n']} cases.\n")
    L.append("## Overall\n")
    L.append("| Metric | Value |\n| --- | --- |")
    L.append(f"| Accuracy (exact level) | {pct(s['accuracy'])} |")
    L.append(f"| Within one level | {pct(s['within_one_level'])} |")
    L.append(f"| Macro precision | {pct(s['macro']['precision'])} |")
    L.append(f"| Macro recall | {pct(s['macro']['recall'])} |")
    L.append(f"| Macro F1 | {pct(s['macro']['f1'])} |")
    L.append(f"| Under-triage rate | {pct(s['under_triage_rate'])} |")
    L.append(f"| Over-triage rate | {pct(s['over_triage_rate'])} |")
    L.append(f"| Emergency (red) recall | {pct(s['emergency_recall'])} |")
    L.append(f"| Severe under-triage (red predicted green/yellow) | {s['severe_under_triage']} cases |")
    L.append(f"| Specialist accuracy (yellow + orange, n={s['specialty_n']}) | {pct(s['specialty_accuracy'])} |")
    L.append(f"| Invalid outputs | {s['invalid_outputs']} |")
    lat = s["avg_latency_s"]
    L.append(f"| Average response time | {'n/a' if lat is None else f'{lat:.2f} s'} |\n")

    L.append("## Per severity level\n")
    L.append("| Level | Precision | Recall | F1 | Cases |\n| --- | --- | --- | --- | --- |")
    for lvl in LEVELS:
        c = s["per_class"][lvl]
        L.append(f"| {lvl} | {pct(c['precision'])} | {pct(c['recall'])} | {pct(c['f1'])} | {c['support']} |")

    L.append("\n## Per language\n")
    L.append("| Language | Cases | Accuracy | Macro F1 | Under-triage | Specialist accuracy |\n| --- | --- | --- | --- | --- | --- |")
    for lang, b in s["by_language"].items():
        L.append(f"| {LANG_NAMES.get(lang, lang)} | {b['n']} | {pct(b['accuracy'])} | {pct(b['macro_f1'])} | "
                 f"{pct(b['under_triage'])} | {pct(b['specialty_accuracy'])} |")

    L.append("\n## Confusion matrix (rows = correct level, columns = predicted)\n")
    L.append("| True \\ Predicted | " + " | ".join(LEVELS) + " | invalid |")
    L.append("| --- " * (len(LEVELS) + 2) + "|")
    for lvl, row in zip(LEVELS, s["confusion"]):
        L.append(f"| **{lvl}** | " + " | ".join(str(v) for v in row) + " |")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def save_confusion_png(model: str, s: dict, path: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib not installed, skipping confusion-matrix image)")
        return False
    cols = LEVELS + (["invalid"] if s["invalid_outputs"] else [])
    data = [row[: len(cols)] for row in s["confusion"]]
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    im = ax.imshow(data, cmap="Blues")
    ax.set_xticks(range(len(cols)), cols)
    ax.set_yticks(range(len(LEVELS)), LEVELS)
    ax.set_xlabel("Predicted level")
    ax.set_ylabel("Correct level")
    ax.set_title(f"Triage confusion matrix\n{model}", fontsize=10)
    top = max(max(r) for r in data) or 1
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, v, ha="center", va="center", color="white" if v > top / 2 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return True


def write_comparison(summaries: dict, path: str) -> None:
    models = list(summaries)
    L = ["# Model comparison\n", "| Metric | " + " | ".join(f"`{m}`" for m in models) + " |",
         "| --- " * (len(models) + 1) + "|"]
    metrics = [
        ("Accuracy", lambda s: pct(s["accuracy"])),
        ("Macro F1", lambda s: pct(s["macro"]["f1"])),
        ("Under-triage rate", lambda s: pct(s["under_triage_rate"])),
        ("Over-triage rate", lambda s: pct(s["over_triage_rate"])),
        ("Emergency recall", lambda s: pct(s["emergency_recall"])),
        ("Severe under-triage (cases)", lambda s: str(s["severe_under_triage"])),
        ("Specialist accuracy", lambda s: pct(s["specialty_accuracy"])),
        ("Avg response time", lambda s: "n/a" if s["avg_latency_s"] is None else f"{s['avg_latency_s']:.2f} s"),
    ]
    for lang in ("en", "hi", "mr"):
        metrics.append((f"Accuracy, {LANG_NAMES[lang]}",
                        lambda s, l=lang: pct(s["by_language"].get(l, {}).get("accuracy"))))
    for name, fn in metrics:
        L.append(f"| {name} | " + " | ".join(fn(summaries[m]) for m in models) + " |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def safe_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def main():
    ap = argparse.ArgumentParser(description="MediAid triage accuracy report")
    ap.add_argument("--models", default=config.GROQ_MODEL, help="comma-separated Groq model IDs")
    ap.add_argument("--data", default="data/test_cases.csv")
    ap.add_argument("--limit", type=int, default=None, help="only the first N cases (quick check)")
    ap.add_argument("--language", choices=["en", "hi", "mr"], help="only one language")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between calls (avoid rate limits)")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    from app.llm import GroqLLM  # needs a key; imported here so --help works without one

    cases = load_cases(args.data)
    if args.language:
        cases = [c for c in cases if c["language"] == args.language]
    if args.limit:
        cases = cases[: args.limit]
    os.makedirs(args.out, exist_ok=True)

    summaries = {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"\n=== {model}: {len(cases)} cases ===")
        rows = run_model(GroqLLM(model=model), model, cases, args.delay)
        s = summarise(rows)
        summaries[model] = s
        name = safe_name(model)

        with open(os.path.join(args.out, f"predictions_{name}.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        write_report(model, s, os.path.join(args.out, f"report_{name}.md"), args.data)
        save_confusion_png(model, s, os.path.join(args.out, f"confusion_{name}.png"))
        with open(os.path.join(args.out, f"summary_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)

        print(f"\n  Accuracy {pct(s['accuracy'])} | Macro F1 {pct(s['macro']['f1'])} | "
              f"Under-triage {pct(s['under_triage_rate'])} | Emergency recall {pct(s['emergency_recall'])} | "
              f"Specialist {pct(s['specialty_accuracy'])} | Invalid {s['invalid_outputs']}")

    if len(summaries) > 1:
        write_comparison(summaries, os.path.join(args.out, "comparison.md"))
    print(f"\nReports saved in the '{args.out}' folder.")


if __name__ == "__main__":
    main()
