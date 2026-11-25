"""Accuracy report for the RAG remedies module.

  python evaluate_rag.py                 retrieval only (no Groq key needed)
  python evaluate_rag.py --llm           + Groq re-ranking (picks the entry or "none")
  python evaluate_rag.py --llm --generate   + full answers, checks for made-up medicines

Writes results/rag_report.md and results/rag_predictions.csv.
"""
import argparse
import csv
import os
import time
from datetime import datetime

from app.rag import MIN_SCORE, RemedyRAG, select_entry

LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
ADULT = {"age_years": 30, "sex": "male", "allergies": [], "current_medicines": [], "conditions": []}


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/rag_test.csv")
    ap.add_argument("--mode", default="auto", choices=["auto", "tfidf", "hybrid"], help="retrieval method")
    ap.add_argument("--llm", action="store_true", help="also test Groq re-ranking")
    ap.add_argument("--generate", action="store_true", help="also generate full answers (needs --llm)")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    llm = None
    if args.llm:
        from app.llm import GroqLLM
        llm = GroqLLM()
    rag = RemedyRAG(llm=llm, retrieval_mode=args.mode)
    with open(args.data, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    os.makedirs(args.out, exist_ok=True)
    print(f"Retrieval: {rag.retriever.mode}   Queries: {len(rows)}   Groq: {'yes' if llm else 'no'}\n")

    out = []
    for i, r in enumerate(rows, 1):
        cands = rag.retriever.search(r["query"], k=3)
        ids = [c["id"] for c in cands]
        gold = r["gold_entry"]
        rank = ids.index(gold) + 1 if gold in ids else None
        rec = {"id": r["id"], "language": r["language"], "query": r["query"], "gold": gold,
               "top1": ids[0], "top3": "|".join(ids), "top1_score": cands[0]["score"], "rank": rank or "",
               "fallback_pick": ids[0] if cands[0]["score"] >= MIN_SCORE else "none"}
        if llm:
            entry, conf, _ = select_entry(llm, r["query"], cands)
            rec["llm_pick"] = entry["id"] if entry else "none"
            rec["llm_confidence"] = conf
            if args.generate and entry is not None:
                res = rag.get_remedies(text=r["query"], profile=ADULT, triage={"level": "green"},
                                       language=r["language"])
                rec["medicines"] = "|".join(m["id"] for m in res.get("medicines", []))
                rec["ungrounded"] = len(res.get("ungrounded_dropped", []))
                rec["generated_by"] = res.get("generated_by", "")
            time.sleep(args.delay)
        out.append(rec)
        pick = rec.get("llm_pick", rec["fallback_pick"])
        print(f"  [{i:>2}/{len(rows)}] {r['id']} {'OK  ' if pick == gold else 'MISS'} gold={gold:<17} pick={pick}")

    pos = [x for x in out if x["gold"] != "none"]
    neg = [x for x in out if x["gold"] == "none"]
    top1 = sum(x["top1"] == x["gold"] for x in pos) / len(pos)
    top3 = sum(bool(x["rank"]) for x in pos) / len(pos)
    mrr = sum(1 / x["rank"] for x in pos if x["rank"]) / len(pos)
    fb_acc = sum(x["fallback_pick"] == x["gold"] for x in out) / len(out)

    L = [f"# MediAid RAG accuracy report\n",
         f"Run on {datetime.now():%Y-%m-%d %H:%M}. Retrieval: `{rag.retriever.mode}`. "
         f"{len(out)} queries ({len(pos)} with a matching entry, {len(neg)} with no matching entry).\n",
         "## Retrieval\n", "| Metric | Value |", "| --- | --- |",
         f"| Top-1 accuracy | {pct(top1)} |", f"| Top-3 recall | {pct(top3)} |", f"| MRR | {mrr:.3f} |",
         f"| Entry choice without Groq (score threshold {MIN_SCORE}) | {pct(fb_acc)} |"]
    if llm:
        acc = sum(x["llm_pick"] == x["gold"] for x in out) / len(out)
        pos_acc = sum(x["llm_pick"] == x["gold"] for x in pos) / len(pos)
        none_acc = sum(x["llm_pick"] == "none" for x in neg) / len(neg) if neg else None
        L += ["\n## Retrieval + Groq re-ranking\n", "| Metric | Value |", "| --- | --- |",
              f"| Overall accuracy (all {len(out)} queries) | {pct(acc)} |",
              f"| Correct entry when one exists | {pct(pos_acc)} |",
              f"| Correctly said \"none\" when nothing fits | {pct(none_acc)} |"]
        if args.generate:
            gen = [x for x in out if "ungrounded" in x]
            bad = sum(x["ungrounded"] > 0 for x in gen)
            meds = sum(x["ungrounded"] for x in gen)
            L += [f"| Answers generated | {len(gen)} |",
                  f"| Answers with a made-up medicine (dropped by grounding check) | {bad} ({pct(bad / len(gen) if gen else None)}) |",
                  f"| Made-up medicine mentions dropped | {meds} |"]
    L += ["\n## Per language\n", "| Language | Queries | Top-1 | Top-3 |" + (" With Groq |" if llm else ""),
          "| --- | --- | --- | --- |" + (" --- |" if llm else "")]
    for lang in ("en", "hi", "mr"):
        p = [x for x in pos if x["language"] == lang]
        a = [x for x in out if x["language"] == lang]
        if not p:
            continue
        line = (f"| {LANG_NAMES[lang]} | {len(a)} | {pct(sum(x['top1'] == x['gold'] for x in p) / len(p))} | "
                f"{pct(sum(bool(x['rank']) for x in p) / len(p))} |")
        if llm:
            line += f" {pct(sum(x['llm_pick'] == x['gold'] for x in a) / len(a))} |"
        L.append(line)
    with open(os.path.join(args.out, "rag_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(args.out, "rag_predictions.csv"), "w", newline="", encoding="utf-8-sig") as f:
        keys = list(dict.fromkeys(k for x in out for k in x))
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    print("\n" + "\n".join(L))
    print(f"\nSaved {args.out}/rag_report.md and {args.out}/rag_predictions.csv")


if __name__ == "__main__":
    main()
