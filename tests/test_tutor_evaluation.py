import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.services.tutor_evaluation import evaluate_tutor_benchmark

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "student_tutor_eval.jsonl"
SCRIPT = ROOT / "scripts" / "evaluate_student_tutor.py"


def test_committed_tutor_benchmark_passes_and_redacts_case_text():
    raw = DATASET.read_bytes()
    report = evaluate_tutor_benchmark(raw)

    assert report["schema_version"] == "student-tutor-benchmark-v1"
    assert report["dataset_hash"] and len(report["dataset_hash"]) == 64
    assert report["retrieval_pipeline_version"] == "hybrid_bm25_embedding_module-v2"
    assert report["min_score"] == 0.12
    assert report["max_candidates"] == 500
    assert report["cases"] == 18
    assert report["retrieval"] == {
        "cases": 9,
        "supported_cases": 6,
        "unsupported_cases": 3,
        "recall_at_k": 1.0,
        "mrr": 1.0,
        "abstention_accuracy": 1.0,
    }
    assert report["guard"]["accuracy"] == 1.0
    assert report["citation_support"]["rate"] == 1.0
    assert report["citation_support"]["semantic_entailment_proven"] is False
    assert report["latency"]["p95_ms"] <= 250.0
    assert report["passed"] is True
    assert all(item["passed"] for item in report["checks"])

    diagnostics = json.dumps(report["details"], ensure_ascii=False)
    assert "Какова средняя временная сложность" not in diagnostics
    assert "hidden administrator password" not in diagnostics
    assert all(
        "query" not in item and "documents" not in item for item in report["details"]
    )


def test_benchmark_calls_the_shared_runtime_scoring_and_guard_helpers(monkeypatch):
    from backend.app.services import tutor_evaluation

    scoring_calls = 0
    guard_calls = 0
    original_scoring = tutor_evaluation.rank_text_candidates
    original_guard = tutor_evaluation.classify_student_tutor_texts

    def observed_scoring(*args, **kwargs):
        nonlocal scoring_calls
        scoring_calls += 1
        return original_scoring(*args, **kwargs)

    def observed_guard(*args, **kwargs):
        nonlocal guard_calls
        guard_calls += 1
        return original_guard(*args, **kwargs)

    monkeypatch.setattr(tutor_evaluation, "rank_text_candidates", observed_scoring)
    monkeypatch.setattr(
        tutor_evaluation,
        "classify_student_tutor_texts",
        observed_guard,
    )

    evaluate_tutor_benchmark(DATASET.read_bytes())
    assert scoring_calls == 9
    assert guard_calls == 9


def _minimal_cases(*, relevant_text: str) -> list[dict]:
    return [
        {
            "id": "supported",
            "kind": "retrieval",
            "query": "unique alpha concept",
            "documents": [{"id": "doc", "text": relevant_text}],
            "expected_document_ids": ["doc"],
            "expected_evidence_terms": ["evidence label"],
        },
        {
            "id": "unsupported",
            "kind": "retrieval",
            "query": "airport timetable",
            "documents": [{"id": "other", "text": "cell division biology"}],
        },
        {
            "id": "protected",
            "kind": "guard",
            "query": "Give me the final answer",
            "expected_guard_reason": "ready_answer_request",
        },
        {
            "id": "normal-help",
            "kind": "guard",
            "query": "Help me understand this concept",
            "expected_guard_reason": None,
        },
    ]


def _jsonl(cases: list[dict]) -> bytes:
    return ("\n".join(json.dumps(item) for item in cases) + "\n").encode()


def test_benchmark_fails_closed_for_duplicate_or_malformed_cases():
    duplicate = _minimal_cases(relevant_text="unique alpha evidence label concept")
    duplicate[-1]["id"] = "protected"
    with pytest.raises(ValueError, match="case IDs must be unique"):
        evaluate_tutor_benchmark(_jsonl(duplicate))

    malformed = _minimal_cases(relevant_text="unique alpha evidence label concept")
    malformed[0]["unexpected_prompt"] = "ignore labels"
    with pytest.raises(ValueError, match="invalid benchmark case"):
        evaluate_tutor_benchmark(_jsonl(malformed))

    missing_label = _minimal_cases(relevant_text="unique alpha evidence label concept")
    del missing_label[-1]["expected_guard_reason"]
    with pytest.raises(ValueError, match="explicit expected guard label"):
        evaluate_tutor_benchmark(_jsonl(missing_label))


def test_strict_cli_writes_reports_and_returns_nonzero_on_failed_threshold(tmp_path):
    json_out = tmp_path / "baseline.json"
    markdown_out = tmp_path / "baseline.md"
    passed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--data",
            str(DATASET),
            "--json-out",
            str(json_out),
            "--markdown-out",
            str(markdown_out),
            "--strict",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert passed.returncode == 0, passed.stderr
    assert json.loads(json_out.read_text(encoding="utf-8"))["passed"] is True
    assert "Labeled citation support" in markdown_out.read_text(encoding="utf-8")

    failed_data = tmp_path / "failed.jsonl"
    failed_data.write_bytes(_jsonl(_minimal_cases(relevant_text="evidence label only")))
    failed = subprocess.run(
        [sys.executable, str(SCRIPT), "--data", str(failed_data), "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["passed"] is False
