from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .course_qa import classify_student_tutor_texts
from .course_retrieval import RETRIEVAL_PIPELINE_VERSION, rank_text_candidates
from .embedding_provider import HashingProvider

BENCHMARK_SCHEMA_VERSION = "student-tutor-benchmark-v1"
BENCHMARK_MAX_CANDIDATES = 500
TUTOR_BENCHMARK_THRESHOLDS = {
    "retrieval_recall_at_k": 0.9,
    "retrieval_mrr": 0.9,
    "abstention_accuracy": 1.0,
    "assessment_guard_accuracy": 1.0,
    "labeled_citation_support": 1.0,
    "offline_case_p95_ms": 250.0,
}


class TutorBenchmarkDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    text: str = Field(min_length=3, max_length=8000)


class TutorBenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    kind: Literal["retrieval", "guard"]
    query: str = Field(min_length=3, max_length=2000)
    documents: list[TutorBenchmarkDocument] = Field(default_factory=list, max_length=20)
    expected_document_ids: list[str] = Field(default_factory=list, max_length=10)
    expected_evidence_terms: list[str] = Field(default_factory=list, max_length=10)
    assessment_item_texts: list[str] = Field(default_factory=list, max_length=10)
    assessment_source_texts: list[str] = Field(default_factory=list, max_length=10)
    expected_guard_reason: (
        Literal[
            "ready_answer_request",
            "assessment_item_match",
            "assessment_source_match",
        ]
        | None
    ) = None
    top_k: int = Field(default=3, ge=1, le=8)

    @model_validator(mode="after")
    def validate_case_contract(self) -> "TutorBenchmarkCase":
        if self.kind == "retrieval":
            if not self.documents:
                raise ValueError("retrieval case requires documents")
            document_ids = [item.id for item in self.documents]
            if len(document_ids) != len(set(document_ids)):
                raise ValueError("document IDs must be unique within a case")
            unknown = set(self.expected_document_ids).difference(document_ids)
            if unknown:
                raise ValueError("expected document IDs must exist in documents")
            if self.expected_document_ids and not self.expected_evidence_terms:
                raise ValueError("supported retrieval case requires evidence terms")
            if self.assessment_item_texts or self.assessment_source_texts:
                raise ValueError("retrieval case cannot contain assessment labels")
        else:
            if (
                self.documents
                or self.expected_document_ids
                or self.expected_evidence_terms
            ):
                raise ValueError("guard case cannot contain retrieval labels")
            if "expected_guard_reason" not in self.model_fields_set:
                raise ValueError("guard case requires an explicit expected guard label")
            if (
                self.expected_guard_reason == "assessment_item_match"
                and not self.assessment_item_texts
            ):
                raise ValueError(
                    "assessment-item guard case requires labeled item text"
                )
            if (
                self.expected_guard_reason == "assessment_source_match"
                and not self.assessment_source_texts
            ):
                raise ValueError(
                    "assessment-source guard case requires labeled source text"
                )
        return self


def tutor_benchmark_path() -> Path:
    configured = (
        os.getenv("STUDENT_TUTOR_EVAL_DATASET", "").strip()
        or os.getenv("COURSE_EVAL_DATASET", "").strip()
    )
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "data" / "student_tutor_eval.jsonl"


def _load_cases(raw: bytes) -> list[TutorBenchmarkCase]:
    cases: list[TutorBenchmarkCase] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(TutorBenchmarkCase.model_validate(json.loads(line)))
        except Exception as exc:
            raise ValueError(
                f"invalid benchmark case on line {line_number}: {exc}"
            ) from exc
    if not cases:
        raise ValueError("benchmark dataset is empty")
    ids = [item.id for item in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("benchmark case IDs must be unique")
    retrieval = [item for item in cases if item.kind == "retrieval"]
    guard = [item for item in cases if item.kind == "guard"]
    if not retrieval or not guard:
        raise ValueError("benchmark requires retrieval and guard cases")
    if not any(item.expected_document_ids for item in retrieval):
        raise ValueError("benchmark requires supported retrieval cases")
    if not any(not item.expected_document_ids for item in retrieval):
        raise ValueError("benchmark requires unsupported retrieval cases")
    if not any(item.expected_guard_reason for item in guard):
        raise ValueError("benchmark requires protected guard cases")
    if not any(item.expected_guard_reason is None for item in guard):
        raise ValueError("benchmark requires normal-help guard cases")
    return cases


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower().replace("ё", "е")
    return re.sub(r"\s+", " ", normalized).strip()


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def evaluate_tutor_benchmark(
    raw: bytes,
    *,
    dataset_name: str = "student_tutor_eval.jsonl",
    min_score: float = 0.12,
) -> dict:
    cases = _load_cases(raw)
    provider = HashingProvider()
    retrieval_hits = 0
    reciprocal_rank = 0.0
    supported_total = 0
    abstention_correct = 0
    abstention_total = 0
    guard_correct = 0
    guard_total = 0
    protected_total = 0
    citation_support_correct = 0
    citation_support_total = 0
    latencies: list[float] = []
    details: list[dict] = []

    for case in cases:
        started = perf_counter()
        detail: dict = {"case_id": case.id, "kind": case.kind}
        if case.kind == "retrieval":
            texts = [item.text for item in case.documents]
            candidates, _ = rank_text_candidates(
                case.query,
                texts,
                document_keys=[item.id for item in case.documents],
                chunk_orders=list(range(len(case.documents))),
                top_k=case.top_k,
                max_candidates=BENCHMARK_MAX_CANDIDATES,
                min_score=min_score,
                embedding_provider=provider,
            )
            predicted = [case.documents[item.index].id for item in candidates]
            expected = set(case.expected_document_ids)
            detail.update(
                {
                    "expected_document_ids": sorted(expected),
                    "predicted_document_ids": predicted,
                }
            )
            if expected:
                supported_total += 1
                match_rank = next(
                    (
                        index
                        for index, document_id in enumerate(predicted, start=1)
                        if document_id in expected
                    ),
                    None,
                )
                if match_rank is not None:
                    retrieval_hits += 1
                    reciprocal_rank += 1.0 / match_rank
                selected_text = " ".join(
                    item.text for item in case.documents if item.id in predicted
                )
                normalized_evidence = _normalize(selected_text)
                support_ok = all(
                    _normalize(term) in normalized_evidence
                    for term in case.expected_evidence_terms
                )
                citation_support_total += 1
                citation_support_correct += int(support_ok)
                detail["labeled_citation_support"] = support_ok
                detail["passed"] = match_rank is not None and support_ok
            else:
                abstention_total += 1
                abstained = not predicted
                abstention_correct += int(abstained)
                detail["passed"] = abstained
        else:
            predicted_reason = classify_student_tutor_texts(
                case.query,
                assessment_item_texts=case.assessment_item_texts,
                assessment_source_texts=case.assessment_source_texts,
            )
            guard_total += 1
            protected_total += int(case.expected_guard_reason is not None)
            correct = predicted_reason == case.expected_guard_reason
            guard_correct += int(correct)
            detail.update(
                {
                    "expected_guard_reason": case.expected_guard_reason,
                    "predicted_guard_reason": predicted_reason,
                    "passed": correct,
                }
            )
        elapsed_ms = (perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        detail["latency_ms"] = round(elapsed_ms, 4)
        details.append(detail)

    report = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "dataset_name": dataset_name,
        "dataset_hash": hashlib.sha256(raw).hexdigest(),
        "embedding_model": provider.embedding_model,
        "retrieval_pipeline_version": RETRIEVAL_PIPELINE_VERSION,
        "min_score": min_score,
        "max_candidates": BENCHMARK_MAX_CANDIDATES,
        "cases": len(cases),
        "retrieval": {
            "cases": supported_total + abstention_total,
            "supported_cases": supported_total,
            "unsupported_cases": abstention_total,
            "recall_at_k": round(retrieval_hits / supported_total, 4),
            "mrr": round(reciprocal_rank / supported_total, 4),
            "abstention_accuracy": round(abstention_correct / abstention_total, 4),
        },
        "guard": {
            "cases": guard_total,
            "protected_cases": protected_total,
            "normal_help_cases": guard_total - protected_total,
            "accuracy": round(guard_correct / guard_total, 4),
        },
        "citation_support": {
            "cases": citation_support_total,
            "rate": round(citation_support_correct / citation_support_total, 4),
            "method": "labeled lexical support in selected synthetic evidence",
            "semantic_entailment_proven": False,
        },
        "latency": {
            "cases": len(latencies),
            "p95_ms": round(_p95(latencies), 4),
            "max_ms": round(max(latencies, default=0.0), 4),
            "scope": "offline retrieval and guard evaluation; excludes model and network",
        },
        "details": details,
    }
    report["checks"] = tutor_benchmark_checks(report)
    report["passed"] = all(item["passed"] for item in report["checks"])
    return report


def tutor_benchmark_checks(report: dict) -> list[dict]:
    values = {
        "retrieval_recall_at_k": report["retrieval"]["recall_at_k"],
        "retrieval_mrr": report["retrieval"]["mrr"],
        "abstention_accuracy": report["retrieval"]["abstention_accuracy"],
        "assessment_guard_accuracy": report["guard"]["accuracy"],
        "labeled_citation_support": report["citation_support"]["rate"],
        "offline_case_p95_ms": report["latency"]["p95_ms"],
    }
    labels = {
        "retrieval_recall_at_k": "Tutor retrieval Recall@K",
        "retrieval_mrr": "Tutor retrieval MRR",
        "abstention_accuracy": "Unsupported-question abstention",
        "assessment_guard_accuracy": "Assessment guard accuracy",
        "labeled_citation_support": "Labeled citation support",
        "offline_case_p95_ms": "Offline tutor case p95 latency",
    }
    checks = []
    for check_id, value in values.items():
        operator = "<=" if check_id == "offline_case_p95_ms" else ">="
        threshold = TUTOR_BENCHMARK_THRESHOLDS[check_id]
        passed = value <= threshold if operator == "<=" else value >= threshold
        checks.append(
            {
                "check_id": check_id,
                "label": labels[check_id],
                "value": value,
                "threshold": threshold,
                "operator": operator,
                "passed": passed,
                "required": True,
            }
        )
    return checks


def tutor_benchmark_markdown(report: dict) -> str:
    lines = [
        "# Student tutor readiness benchmark",
        "",
        f"- Status: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Schema: `{report['schema_version']}`",
        f"- Dataset: `{report['dataset_name']}`",
        f"- SHA-256: `{report['dataset_hash']}`",
        f"- Cases: {report['cases']}",
        f"- Embeddings: `{report['embedding_model']}`",
        "",
        "## Required checks",
        "",
        "| Check | Result | Threshold | Status |",
        "|---|---:|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['label']} | {check['value']} | "
            f"{check['operator']} {check['threshold']} | "
            f"{'PASS' if check['passed'] else 'FAIL'} |"
        )
    failed = [item["case_id"] for item in report["details"] if not item["passed"]]
    lines.extend(
        [
            "",
            "## Failed cases",
            "",
            ", ".join(f"`{item}`" for item in failed) if failed else "None.",
            "",
            "## Methodology limits",
            "",
            "- The dataset is synthetic and is a regression gate, not an independent production acceptance sample.",
            "- Labeled citation support is a lexical evidence proxy; it does not prove semantic entailment.",
            "- Latency excludes database, network, hosted model, and Canvas integration time.",
            "- Case diagnostics contain synthetic IDs and outcomes, not questions or source text.",
        ]
    )
    return "\n".join(lines).strip() + "\n"
