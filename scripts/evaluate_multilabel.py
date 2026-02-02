import argparse
import json
from pathlib import Path
from typing import Iterable

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.utils.bloom import classify_bloom_multilabel


LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


def _vectorize(labels: Iterable[str]) -> list[int]:
    label_set = {lbl for lbl in labels}
    return [1 if lvl in label_set else 0 for lvl in LEVELS]


def _hamming_loss(y_true: list[list[int]], y_pred: list[list[int]]) -> float:
    if not y_true:
        return 0.0
    total = 0
    for t, p in zip(y_true, y_pred):
        total += sum(1 for tv, pv in zip(t, p) if tv != pv)
    return total / (len(y_true) * len(LEVELS))


def _f1_micro(y_true: list[list[int]], y_pred: list[list[int]]) -> float:
    tp = fp = fn = 0
    for t, p in zip(y_true, y_pred):
        for tv, pv in zip(t, p):
            if tv == 1 and pv == 1:
                tp += 1
            elif tv == 0 and pv == 1:
                fp += 1
            elif tv == 1 and pv == 0:
                fn += 1
    denom = (2 * tp + fp + fn)
    return (2 * tp / denom) if denom else 0.0


def _f1_macro(y_true: list[list[int]], y_pred: list[list[int]]) -> float:
    f1s = []
    for idx in range(len(LEVELS)):
        tp = fp = fn = 0
        for t, p in zip(y_true, y_pred):
            tv, pv = t[idx], p[idx]
            if tv == 1 and pv == 1:
                tp += 1
            elif tv == 0 and pv == 1:
                fp += 1
            elif tv == 1 and pv == 0:
                fn += 1
        denom = (2 * tp + fp + fn)
        f1s.append((2 * tp / denom) if denom else 0.0)
    return sum(f1s) / len(f1s)


def load_dataset(path: Path) -> list[dict]:
    items = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/bloom_dataset.jsonl")
    parser.add_argument("--min-prob", type=float, default=0.2)
    parser.add_argument("--max-levels", type=int, default=2)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    dataset = load_dataset(Path(args.data))
    y_true: list[list[int]] = []
    y_pred: list[list[int]] = []

    for item in dataset:
        text = item.get("text", "")
        labels = item.get("labels", [])
        if not text:
            continue
        result = classify_bloom_multilabel(
            text,
            min_prob=args.min_prob,
            max_levels=args.max_levels,
        )
        y_true.append(_vectorize(labels))
        y_pred.append(_vectorize(result["top_levels"]))

    report = {
        "samples": len(y_true),
        "hamming_loss": round(_hamming_loss(y_true, y_pred), 4),
        "f1_micro": round(_f1_micro(y_true, y_pred), 4),
        "f1_macro": round(_f1_macro(y_true, y_pred), 4),
        "min_prob": args.min_prob,
        "max_levels": args.max_levels,
    }

    out_text = json.dumps(report, ensure_ascii=False, indent=2)
    print(out_text)
    if args.out:
        Path(args.out).write_text(out_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
