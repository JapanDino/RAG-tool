from pathlib import Path

from scripts.evaluate_course_copilot import evaluate_cases


def test_course_copilot_retrieval_fixture_has_expected_quality(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    path = Path(__file__).resolve().parents[1] / "data" / "course_copilot_eval.jsonl"
    report = evaluate_cases(path)
    assert report["cases"] == 10
    assert report["recall_at_k"] >= 0.9
    assert report["mrr"] >= 0.9
    assert report["abstention_accuracy"] == 1.0
