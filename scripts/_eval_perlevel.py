"""Extended evaluation: per-level precision/recall/F1 + Cohen kappa."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.services.bloom_multilabel import classify_bloom_multilabel

LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


def vectorize(labels):
    s = set(labels)
    return [1 if lvl in s else 0 for lvl in LEVELS]


def main():
    data_path = Path("data/bloom_dataset.jsonl")
    items = [json.loads(ln) for ln in data_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    y_true, y_pred = [], []
    for it in items:
        if not it.get("text"):
            continue
        res = classify_bloom_multilabel(it["text"], min_prob=0.2, max_levels=2)
        y_true.append(vectorize(it["labels"]))
        y_pred.append(vectorize(res["top_levels"]))

    per_level = {}
    for i, lvl in enumerate(LEVELS):
        tp = sum(1 for t, p in zip(y_true, y_pred) if t[i] == 1 and p[i] == 1)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t[i] == 0 and p[i] == 1)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t[i] == 1 and p[i] == 0)
        support = sum(1 for t in y_true if t[i] == 1)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_level[lvl] = {
            "support": support,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }

    # Cohen kappa (per-level, then averaged)
    kappas = []
    n = len(y_true)
    for i in range(6):
        po = sum(1 for t, p in zip(y_true, y_pred) if t[i] == p[i]) / n
        p1_true = sum(t[i] for t in y_true) / n
        p1_pred = sum(p[i] for p in y_pred) / n
        pe = p1_true * p1_pred + (1 - p1_true) * (1 - p1_pred)
        if pe >= 1:
            kappas.append(1.0 if po >= 1 else 0.0)
        else:
            kappas.append((po - pe) / (1 - pe))
    kappa_macro = sum(kappas) / len(kappas)

    # global metrics
    tp = sum(1 for t, p in zip(y_true, y_pred) for tv, pv in zip(t, p) if tv == 1 and pv == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) for tv, pv in zip(t, p) if tv == 0 and pv == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) for tv, pv in zip(t, p) if tv == 1 and pv == 0)
    f1_micro = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    hamming = sum(1 for t, p in zip(y_true, y_pred) for tv, pv in zip(t, p) if tv != pv) / (n * 6)

    out = {
        "samples": n,
        "hamming_loss": round(hamming, 4),
        "f1_micro": round(f1_micro, 4),
        "f1_macro": round(sum(v["f1"] for v in per_level.values()) / 6, 4),
        "cohen_kappa_macro": round(kappa_macro, 4),
        "per_level": per_level,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path("data/eval_report_full.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
