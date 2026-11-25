"""Accuracy metrics for triage evaluation (no sklearn needed)."""
from app.triage import LEVELS

RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
REFERRAL_LEVELS = ("yellow", "orange")  # specialist accuracy is measured on these


def confusion_matrix(gold: list, pred: list) -> list[list[int]]:
    """Rows = true level, columns = predicted level (+ last column 'invalid')."""
    m = [[0] * (len(LEVELS) + 1) for _ in LEVELS]
    for g, p in zip(gold, pred):
        col = RANK.get(p, len(LEVELS))
        m[RANK[g]][col] += 1
    return m


def per_class(gold: list, pred: list) -> dict:
    out = {}
    for lvl in LEVELS:
        tp = sum(g == lvl and p == lvl for g, p in zip(gold, pred))
        fp = sum(g != lvl and p == lvl for g, p in zip(gold, pred))
        fn = sum(g == lvl and p != lvl for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[lvl] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return out


def summarise(rows: list[dict]) -> dict:
    """rows: dicts with gold_level, pred_level, gold_specialty, pred_specialty, language, latency_s."""
    n = len(rows)
    gold = [r["gold_level"] for r in rows]
    pred = [r["pred_level"] for r in rows]
    valid = [p in RANK for p in pred]

    correct = sum(g == p for g, p in zip(gold, pred))
    under = sum(v and RANK[p] < RANK[g] for g, p, v in zip(gold, pred, valid))
    over = sum(v and RANK[p] > RANK[g] for g, p, v in zip(gold, pred, valid))
    severe_under = sum(g == "red" and p in ("green", "yellow") for g, p in zip(gold, pred))
    within_one = sum(v and abs(RANK[p] - RANK[g]) <= 1 for g, p, v in zip(gold, pred, valid))

    pc = per_class(gold, pred)
    macro = {k: sum(pc[l][k] for l in LEVELS) / len(LEVELS) for k in ("precision", "recall", "f1")}

    ref = [r for r in rows if r["gold_level"] in REFERRAL_LEVELS]
    spec_correct = sum(r["pred_specialty"] == r["gold_specialty"] for r in ref)

    by_lang = {}
    for lang in sorted({r["language"] for r in rows}):
        sub = [r for r in rows if r["language"] == lang]
        s_gold = [r["gold_level"] for r in sub]
        s_pred = [r["pred_level"] for r in sub]
        s_ref = [r for r in sub if r["gold_level"] in REFERRAL_LEVELS]
        by_lang[lang] = {
            "n": len(sub),
            "accuracy": sum(g == p for g, p in zip(s_gold, s_pred)) / len(sub),
            "under_triage": sum(p in RANK and RANK[p] < RANK[g] for g, p in zip(s_gold, s_pred)) / len(sub),
            "macro_f1": sum(v["f1"] for v in per_class(s_gold, s_pred).values()) / len(LEVELS),
            "specialty_accuracy": (sum(r["pred_specialty"] == r["gold_specialty"] for r in s_ref) / len(s_ref)) if s_ref else None,
        }

    latencies = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    return {
        "n": n,
        "accuracy": correct / n,
        "within_one_level": within_one / n,
        "under_triage_rate": under / n,
        "over_triage_rate": over / n,
        "severe_under_triage": severe_under,
        "emergency_recall": pc["red"]["recall"],
        "invalid_outputs": n - sum(valid),
        "macro": macro,
        "per_class": pc,
        "specialty_accuracy": spec_correct / len(ref) if ref else None,
        "specialty_n": len(ref),
        "by_language": by_lang,
        "confusion": confusion_matrix(gold, pred),
        "avg_latency_s": sum(latencies) / len(latencies) if latencies else None,
    }
