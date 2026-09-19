"""Compare regressions, not research accuracy: python -m scripts.evaluate_bloom_rubric."""

import argparse
import json
import platform
from importlib.metadata import version
from pathlib import Path

from backend.app.services.bloom_rubric import RUBRIC_VERSION, classify_learning_demands
from backend.app.utils.bloom import _get_morph, classify_bloom_multilabel


def evaluate(cases):
    report = {
        "environment": {
            "python": platform.python_version(),
            "pymorphy3": version("pymorphy3"),
            "pymorphy3_dicts_ru": version("pymorphy3-dicts-ru"),
            "legacy_morphology_available": _get_morph() is not None,
        },
        "rubric_version": RUBRIC_VERSION,
        "cases": len(cases),
        "validation": "Engineering regression cases; not independent expert validation",
        "legacy": {"label_set_matches": 0, "labels_on_no_task": 0},
        "rubric": {
            "label_set_matches": 0,
            "labels_on_no_task": 0,
            "status_matches": 0,
            "abstained_on_ambiguous": 0,
        },
        "no_task_cases": 0,
        "ambiguous_cases": 0,
        "differences": [],
    }
    for case in cases:
        old = classify_bloom_multilabel(case["text"])["top_levels"]
        new = classify_learning_demands(case["text"])
        expected = set(case["levels"])
        report["legacy"]["label_set_matches"] += set(old) == expected
        report["rubric"]["label_set_matches"] += set(new["levels"]) == expected
        report["rubric"]["status_matches"] += new["status"] == case["status"]
        if case["status"] == "no_task":
            report["no_task_cases"] += 1
            report["legacy"]["labels_on_no_task"] += bool(old)
            report["rubric"]["labels_on_no_task"] += bool(new["levels"])
        if case["status"] == "needs_review":
            report["ambiguous_cases"] += 1
            report["rubric"]["abstained_on_ambiguous"] += not new["levels"]
        if set(old) != set(new["levels"]):
            report["differences"].append(
                {
                    "id": case["id"],
                    "legacy": old,
                    "rubric": new["levels"],
                    "expected": case["levels"],
                }
            )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=Path("data/bloom_rubric_cases.jsonl")
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in args.cases.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = evaluate(cases)
    result = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    print(result)
