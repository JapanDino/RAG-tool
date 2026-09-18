from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from scripts.evaluate_instructor_drafts import evaluate_cases


def test_default_instructor_draft_safety_protocol_passes():
    report = evaluate_cases(Path("data/instructor_draft_eval.jsonl"))

    assert report["cases"] == 8
    assert report["safety_accuracy"] == 1.0
    assert report["answer_leakage_cases"] == 0
    assert report["passed"] is True
