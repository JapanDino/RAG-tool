from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.services.research_protocol import (
    ResearchCourseRegistry,
    ResearchProtocol,
    assign_blinded_course_splits,
    canonical_protocol_bytes,
    load_research_protocol,
    protocol_blockers,
    protocol_sha256,
    research_protocol_markdown,
    research_protocol_report,
    verify_committed_datasets,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = (
    REPO_ROOT / "research" / "protocols" / "teacher_calibrated_multilingual_rag_v1.json"
)
EXPECTED_PROTOCOL_SHA256 = (
    "0772898f365df58300f15f45912f61e83633534b629269694f33f0688f99dddd"
)


def _payload() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _dataset(payload: dict, dataset_id: str) -> dict:
    return next(item for item in payload["datasets"] if item["id"] == dataset_id)


def _course_registry_payload(*, count_per_language: int = 40) -> dict:
    courses = [
        {"opaque_course_id": f"course_{index:012x}", "language": "ru"}
        for index in range(count_per_language)
    ]
    courses.extend(
        {
            "opaque_course_id": f"course_{index + 1000:012x}",
            "language": "en",
        }
        for index in range(count_per_language)
    )
    return {
        "schema_version": "research-course-registry.v1",
        "protocol_id": "teacher_calibrated_multilingual_rag_v1",
        "labels_inspected": False,
        "contains_outcomes": False,
        "courses": courses,
    }


def test_frozen_protocol_is_canonical_reproducible_and_explicitly_not_ready():
    protocol = load_research_protocol(PROTOCOL_PATH)
    verify_committed_datasets(protocol, REPO_ROOT)
    assert protocol_sha256(protocol) == EXPECTED_PROTOCOL_SHA256
    assert canonical_protocol_bytes(protocol) == canonical_protocol_bytes(
        load_research_protocol(PROTOCOL_PATH)
    )

    report = research_protocol_report(protocol, repo_root=REPO_ROOT)
    assert report["analysis_ready"] is False
    assert report["collection_allowed"] is False
    assert report["currently_supported_claim"] == (
        "protocol_only_no_effectiveness_evidence"
    )
    assert "approval:institutional_ethics" in report["blockers"]
    assert "dataset:teacher_courses_test_v1" in report["blockers"]
    assert "version:model_and_provider" in report["blockers"]
    assert {item["id"] for item in report["conditions"]} == {
        "canvas_search_baseline",
        "standard_course_rag",
        "bounded_role_aware_agent",
    }
    assert len(report["primary_endpoints"]) == 5


def test_synthetic_sources_are_hash_verified_and_never_confirmatory():
    protocol = load_research_protocol(PROTOCOL_PATH)
    synthetic = [
        item
        for item in protocol.datasets
        if item.evidence_class == "synthetic_regression"
    ]
    assert len(synthetic) == 4
    assert all(item.status == "committed" for item in synthetic)
    assert all(item.confirmatory_eligible is False for item in synthetic)
    assert all(item.contains_real_course_data is False for item in synthetic)
    verify_committed_datasets(protocol, REPO_ROOT)


def test_protocol_rejects_unknown_fields_duplicate_ids_and_missing_baselines():
    unknown = _payload()
    unknown["observed_results"] = {"effect": 1.0}
    with pytest.raises(ValidationError):
        ResearchProtocol.model_validate(unknown)

    duplicate = _payload()
    duplicate["conditions"].append(copy.deepcopy(duplicate["conditions"][0]))
    with pytest.raises(ValidationError, match="duplicate condition"):
        ResearchProtocol.model_validate(duplicate)

    missing = _payload()
    missing["conditions"] = [
        item for item in missing["conditions"] if item["id"] != "standard_course_rag"
    ]
    replacement = copy.deepcopy(missing["conditions"][-1])
    replacement["id"] = "unregistered_alternative"
    missing["conditions"].append(replacement)
    with pytest.raises(ValidationError, match="standard-RAG"):
        ResearchProtocol.model_validate(missing)

    swapped_kinds = _payload()
    swapped_kinds["conditions"][0]["kind"] = "candidate"
    swapped_kinds["conditions"][2]["kind"] = "non_agent_baseline"
    with pytest.raises(ValidationError, match="kinds cannot be changed"):
        ResearchProtocol.model_validate(swapped_kinds)

    unsupported_claim = _payload()
    unsupported_claim["claim"]["confirmatory"] = (
        "This bundled synthetic regression proves classroom effectiveness and "
        "learning improvement for every student."
    )
    with pytest.raises(ValidationError):
        ResearchProtocol.model_validate(unsupported_claim)


def test_protocol_rejects_course_split_leakage_and_nonopaque_course_ids():
    leaking = _payload()
    _dataset(leaking, "teacher_courses_train_v1")["opaque_course_ids"] = [
        "course_0123456789ab"
    ]
    _dataset(leaking, "teacher_courses_test_v1")["opaque_course_ids"] = [
        "course_0123456789ab"
    ]
    with pytest.raises(ValidationError, match="split leakage"):
        ResearchProtocol.model_validate(leaking)

    direct_identifier = _payload()
    _dataset(direct_identifier, "teacher_courses_train_v1")["opaque_course_ids"] = [
        "canvas-course-42"
    ]
    with pytest.raises(ValidationError, match="opaque"):
        ResearchProtocol.model_validate(direct_identifier)


def test_protocol_rejects_test_tuning_and_synthetic_effectiveness_upgrade():
    tuning = _payload()
    tuning["split_policy"]["final_test_policy"] = "retune_after_test"
    with pytest.raises(ValidationError):
        ResearchProtocol.model_validate(tuning)

    synthetic_claim = _payload()
    _dataset(synthetic_claim, "student_tutor_synthetic_v1")[
        "confirmatory_eligible"
    ] = True
    with pytest.raises(ValidationError, match="engineering-only"):
        ResearchProtocol.model_validate(synthetic_claim)


def test_collection_and_minors_fail_closed_before_approval():
    collection = _payload()
    collection["ethics"]["collection_allowed"] = True
    with pytest.raises(ValidationError):
        ResearchProtocol.model_validate(collection)

    minors = _payload()
    minors["ethics"]["minors_in_initial_confirmatory_study"] = True
    with pytest.raises(ValidationError, match="minors require"):
        ResearchProtocol.model_validate(minors)


@pytest.mark.parametrize(
    "unsafe_value",
    (
        "Contact research.owner@example.org",
        "Bearer abcdefghijklmnop",
        "api_key=super-secret-value",
        "https://user:password@example.org/report",
        "Participant Ivan Ivanov",
        "Call +7 999 123-45-67",
        "Canvas account 123456",
        "grade 2",
    ),
)
def test_protocol_rejects_direct_identifiers_and_secret_shaped_values(unsafe_value):
    payload = _payload()
    payload["limitations"].append(unsafe_value)
    with pytest.raises(ValidationError):
        ResearchProtocol.model_validate(payload)


def test_hash_mismatch_fails_without_changing_the_source_protocol():
    payload = _payload()
    original = PROTOCOL_PATH.read_bytes()
    _dataset(payload, "student_tutor_synthetic_v1")["sha256"] = "0" * 64
    protocol = ResearchProtocol.model_validate(payload)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_committed_datasets(protocol, REPO_ROOT)
    assert PROTOCOL_PATH.read_bytes() == original


def test_markdown_names_blockers_and_disallows_effectiveness_claims():
    report = research_protocol_report(
        load_research_protocol(PROTOCOL_PATH), repo_root=REPO_ROOT
    )
    markdown = research_protocol_markdown(report)
    assert "Analysis ready: **no**" in markdown
    assert "Participant collection allowed: **no**" in markdown
    assert "synthetic_regression / engineering_only" in markdown
    assert "cannot support yet" in markdown
    assert "classroom effectiveness" in markdown
    assert "student@" not in markdown
    assert "expected_answer" not in markdown


def test_cli_exports_deterministically_and_strict_readiness_fails(tmp_path):
    script = REPO_ROOT / "scripts" / "export_research_protocol.py"
    json_one = tmp_path / "one.json"
    json_two = tmp_path / "two.json"
    markdown_one = tmp_path / "one.md"
    source_before = PROTOCOL_PATH.read_bytes()

    first = subprocess.run(
        [
            sys.executable,
            str(script),
            "--json-out",
            str(json_one),
            "--markdown-out",
            str(markdown_one),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [sys.executable, str(script), "--json-out", str(json_two)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    strict = subprocess.run(
        [sys.executable, str(script), "--require-analysis-ready"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert strict.returncode == 2
    assert json_one.read_bytes() == json_two.read_bytes()
    assert b"\r\n" not in json_one.read_bytes()
    assert b"\r\n" not in markdown_one.read_bytes()
    assert json.loads(json_one.read_text(encoding="utf-8"))["analysis_ready"] is False
    assert "Only a frozen, reproducible protocol exists" in markdown_one.read_text(
        encoding="utf-8"
    )
    assert PROTOCOL_PATH.read_bytes() == source_before


def test_blocker_projection_is_sorted_unique_and_content_free():
    blockers = protocol_blockers(load_research_protocol(PROTOCOL_PATH))
    assert blockers == sorted(set(blockers))
    rendered = json.dumps(blockers)
    assert "course text" not in rendered
    assert "participant outcome" not in rendered


def test_blinded_course_split_is_course_isolated_balanced_and_deterministic():
    protocol = load_research_protocol(PROTOCOL_PATH)
    registry_payload = _course_registry_payload()
    registry = ResearchCourseRegistry.model_validate(registry_payload)
    first = assign_blinded_course_splits(protocol, registry)
    registry_payload["courses"].reverse()
    second = assign_blinded_course_splits(
        protocol, ResearchCourseRegistry.model_validate(registry_payload)
    )

    assert first == second
    assert {key: len(value) for key, value in first["splits"].items()} == {
        "train": 48,
        "development": 16,
        "test": 16,
    }
    assert first["language_counts"] == {
        "train": {"ru": 24, "en": 24},
        "development": {"ru": 8, "en": 8},
        "test": {"ru": 8, "en": 8},
    }
    owners = {
        course_id: split
        for split, course_ids in first["splits"].items()
        for course_id in course_ids
    }
    assert len(owners) == 80
    languages = {
        item["opaque_course_id"]: item["language"]
        for item in registry_payload["courses"]
    }
    for split, course_ids in first["splits"].items():
        assert (
            sum(languages[item] == "ru" for item in course_ids) == len(course_ids) // 2
        ), split


def test_course_registry_rejects_outcomes_duplicates_and_sample_shortfall():
    outcomes = _course_registry_payload()
    outcomes["contains_outcomes"] = True
    with pytest.raises(ValidationError):
        ResearchCourseRegistry.model_validate(outcomes)

    duplicate = _course_registry_payload()
    duplicate["courses"].append(copy.deepcopy(duplicate["courses"][0]))
    with pytest.raises(ValidationError, match="duplicate opaque"):
        ResearchCourseRegistry.model_validate(duplicate)

    short = ResearchCourseRegistry.model_validate(
        _course_registry_payload(count_per_language=10)
    )
    with pytest.raises(ValueError, match="total sample-size floor"):
        assign_blinded_course_splits(load_research_protocol(PROTOCOL_PATH), short)


def test_split_cli_writes_only_opaque_metadata(tmp_path):
    registry_path = tmp_path / "registry.json"
    manifest_path = tmp_path / "manifest.json"
    registry_path.write_text(json.dumps(_course_registry_payload()), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "assign_research_course_splits.py"),
            "--registry",
            str(registry_path),
            "--out",
            str(manifest_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["unit"] == "course"
    assert len(manifest["splits"]["test"]) == 16
    rendered = manifest_path.read_text(encoding="utf-8")
    assert "title" not in rendered
    assert "email" not in rendered
    assert "outcome" not in rendered
