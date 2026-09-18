from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTOCOL_SCHEMA_VERSION = "research-protocol.v1"
PROTOCOL_ID = "teacher_calibrated_multilingual_rag_v1"
REQUIRED_CONDITIONS = {
    "canvas_search_baseline",
    "standard_course_rag",
    "bounded_role_aware_agent",
}
REQUIRED_APPROVALS = {
    "institutional_ethics",
    "school_data_protection",
    "participant_consent",
    "minor_assent_and_guardian_consent",
    "opt_out_and_deletion",
}
REQUIRED_VERSION_PINS = {
    "code_revision",
    "dataset_manifest",
    "retrieval_pipeline",
    "workflow_registry",
    "policy_bundle",
    "prompt_bundle",
    "model_and_provider",
    "power_analysis",
}
FORBIDDEN_KEYS = {
    "api_key",
    "answer",
    "canvas_user_id",
    "credential",
    "email",
    "name",
    "password",
    "prompt",
    "question",
    "raw_text",
    "student_id",
    "teacher_id",
    "token",
    "transcript",
}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?:api[_-]?key|password|token)\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"https?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)\+\d[\d\s().-]{8,}\d(?!\w)")
DIRECT_ID_PATTERN = re.compile(
    r"\b(?:canvas|lms|participant|student|teacher|account|user)"
    r"\s*(?:id|account|number)?\s*[:=#-]?\s*\d{3,}\b",
    re.IGNORECASE,
)
GRADE_PATTERN = re.compile(
    r"\b(?:grade|score|mark)\s*[:=#-]?\s*\d+(?:\.\d+)?\b", re.IGNORECASE
)
LABELED_NAME_PATTERN = re.compile(
    r"\b(?i:participant|student|teacher)\s+"
    r"[A-ZА-ЯЁ][a-zа-яё-]+\s+[A-ZА-ЯЁ][a-zа-яё-]+\b"
)
OPAQUE_COURSE_PATTERN = re.compile(r"^course_[a-f0-9]{12}$")


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchClaim(ClosedModel):
    confirmatory: Literal[
        "On held-out teacher-validated Russian and English courses, the bounded role-aware agent improves independently judged supported workflow-task success and adult instructor decision efficiency over standard RAG, improves evidence retrieval over frozen Canvas keyword search, and passes fixed citation-grounding and forbidden-disclosure gates."
    ]
    currently_supported: Literal["protocol_only_no_effectiveness_evidence"]
    prohibited: list[str] = Field(min_length=1, max_length=12)


class Condition(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    kind: Literal["non_agent_baseline", "rag_baseline", "candidate"]
    description: str = Field(min_length=20, max_length=1000)
    controlled_components: list[str] = Field(min_length=1, max_length=20)
    allowed_capabilities: list[str] = Field(min_length=1, max_length=20)


class Endpoint(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    family: Literal[
        "supported_task_quality",
        "grounding",
        "safety",
        "calibration",
        "instructor_efficiency",
        "learner_outcome",
        "operations",
    ]
    role: Literal["learner", "instructor", "cross_role", "system"]
    primary: bool
    metric: str = Field(min_length=3, max_length=120)
    estimand: str = Field(min_length=20, max_length=1000)
    direction: Literal["higher", "lower", "non_inferiority", "descriptive"]
    analysis: str = Field(min_length=20, max_length=1200)


class Hypothesis(ClosedModel):
    id: str = Field(pattern=r"^H[1-9][0-9]*$")
    endpoint_id: str
    candidate_condition_id: str
    comparator_condition_id: str
    statement: str = Field(min_length=30, max_length=1000)
    confirmatory: bool = True


class DatasetRef(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    evidence_class: Literal[
        "synthetic_regression", "teacher_validated", "participant_outcomes"
    ]
    status: Literal["committed", "planned_requires_approval"]
    purpose: Literal[
        "engineering_only",
        "train",
        "development",
        "test",
        "instructor_study",
    ]
    languages: list[Literal["ru", "en"]] = Field(min_length=1, max_length=2)
    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sample_count: int | None = Field(default=None, ge=1)
    split_unit: Literal["course", "engineering_case"]
    opaque_course_ids: list[str] = Field(default_factory=list, max_length=10000)
    contains_real_course_data: bool
    contains_participant_data: bool
    confirmatory_eligible: bool

    @field_validator("languages")
    @classmethod
    def unique_languages(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("dataset languages must be unique")
        return value

    @model_validator(mode="after")
    def validate_dataset_state(self):
        if self.status == "committed":
            if not self.path or not self.sha256 or self.sample_count is None:
                raise ValueError(
                    "committed datasets require path, sha256, and sample_count"
                )
        elif self.path is not None or self.sha256 is not None:
            raise ValueError("planned datasets cannot claim a path or digest")
        if self.evidence_class == "synthetic_regression":
            if self.purpose != "engineering_only" or self.confirmatory_eligible:
                raise ValueError("synthetic datasets are engineering-only")
            if self.split_unit != "engineering_case":
                raise ValueError("synthetic regression uses engineering cases")
            if self.contains_real_course_data or self.contains_participant_data:
                raise ValueError("synthetic regression cannot contain real data")
        else:
            if self.split_unit != "course":
                raise ValueError("real evaluation data must use course-level isolation")
            if self.status != "planned_requires_approval":
                raise ValueError(
                    "real data cannot be committed in the frozen offline protocol"
                )
        for course_id in self.opaque_course_ids:
            if not OPAQUE_COURSE_PATTERN.fullmatch(course_id):
                raise ValueError("course IDs must be opaque course_<12 hex> references")
        return self


class SplitPolicy(ClosedModel):
    unit: Literal["course"]
    train_percent: int = Field(ge=1, le=98)
    development_percent: int = Field(ge=1, le=98)
    test_percent: int = Field(ge=1, le=98)
    language_balance: Literal["stratified_ru_en"]
    assignment: Literal["blinded_hash_before_labels"]
    public_salt: str = Field(pattern=r"^[a-z0-9_-]{8,64}$")
    final_test_policy: Literal["single_locked_evaluation_no_tuning"]

    @model_validator(mode="after")
    def percentages_sum_to_one_hundred(self):
        if self.train_percent + self.development_percent + self.test_percent != 100:
            raise ValueError("split percentages must sum to 100")
        return self


class VersionPin(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    value: str = Field(min_length=1, max_length=300)
    status: Literal["pinned", "pending_before_execution"]

    @model_validator(mode="after")
    def pending_values_are_explicit(self):
        if self.status == "pending_before_execution" and self.value != "PENDING":
            raise ValueError("pending version pins must use the literal PENDING")
        if self.status == "pinned" and self.value == "PENDING":
            raise ValueError("pinned versions need an exact value")
        return self


class ApprovalGate(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    required: bool
    status: Literal["pending", "approved", "not_applicable"]
    evidence_ref: str | None = Field(default=None, pattern=r"^approval_[a-f0-9]{12}$")
    rule: str = Field(min_length=20, max_length=1000)

    @model_validator(mode="after")
    def approval_evidence_matches_status(self):
        if self.status == "approved" and self.evidence_ref is None:
            raise ValueError("approved gates require an opaque evidence reference")
        if self.status != "approved" and self.evidence_ref is not None:
            raise ValueError("unapproved gates cannot carry approval evidence")
        return self


class SampleSizePlan(ClosedModel):
    teacher_validated_courses: int = Field(ge=20)
    courses_per_language_minimum: int = Field(ge=10)
    locked_tasks_per_course_minimum: int = Field(ge=4)
    supported_tasks_per_course_minimum: int = Field(ge=2)
    adversarial_tasks_per_course_minimum: int = Field(ge=1)
    instructor_participants: int = Field(ge=12)
    power: float = Field(gt=0.0, lt=1.0)
    alpha: float = Field(gt=0.0, lt=0.5)
    detectable_standardized_effect: float = Field(gt=0.0, le=2.0)
    detectable_task_completion_difference: float = Field(gt=0.0, lt=1.0)
    detectable_retrieval_recall_difference: float = Field(gt=0.0, lt=1.0)
    retrieval_baseline_rate: float = Field(gt=0.0, lt=1.0)
    assumed_course_icc: float = Field(ge=0.0, lt=1.0)
    rationale: str = Field(min_length=40, max_length=1500)

    @model_validator(mode="after")
    def task_mix_fits_locked_minimum(self):
        if (
            self.supported_tasks_per_course_minimum
            + self.adversarial_tasks_per_course_minimum
            > self.locked_tasks_per_course_minimum
        ):
            raise ValueError("supported and adversarial task floors exceed total tasks")
        return self


class AnalysisPlan(ClosedModel):
    alpha: float = Field(gt=0.0, lt=0.5)
    primary_multiplicity: Literal["holm_bonferroni"]
    confirmatory_family: Literal["H1_H2_H3_holm_bonferroni"]
    confidence_interval: Literal["cluster_bootstrap_by_course_95"]
    analysis_population: Literal["intention_to_treat_and_all_locked_test_cases"]
    missing_data: str = Field(min_length=30, max_length=1500)
    exclusions: list[str] = Field(min_length=1, max_length=20)
    stopping_rule: Literal["fixed_sample_no_outcome_peeking"]
    subgroup_policy: Literal["ru_en_predeclared_secondary_no_retuning"]
    instructor_design: str = Field(min_length=40, max_length=1500)
    safety_gate_policy: str = Field(min_length=40, max_length=1500)
    grounding_gate_policy: str = Field(min_length=40, max_length=1500)
    sample_size: SampleSizePlan


class TeacherCalibrationPlan(ClosedModel):
    source: Literal["teacher_validated_development_courses_only"]
    tunable_components: list[str] = Field(min_length=1, max_length=20)
    locked_test_rule: Literal["no_threshold_prompt_policy_or_retrieval_tuning"]
    adjudication: str = Field(min_length=40, max_length=1200)
    agreement_metric: str = Field(min_length=10, max_length=300)


class EthicsPlan(ClosedModel):
    collection_allowed: Literal[False]
    minors_in_initial_confirmatory_study: bool
    data_minimization: list[str] = Field(min_length=1, max_length=20)
    retention_days: int = Field(ge=1, le=365)
    raw_message_collection: Literal[False]
    personnel_or_student_ranking: Literal[False]
    gates: list[ApprovalGate] = Field(min_length=1, max_length=20)
    adverse_event_rule: str = Field(min_length=30, max_length=1200)


class ReproducibilityPlan(ClosedModel):
    required_run_fields: list[str] = Field(min_length=1, max_length=30)
    version_pins: list[VersionPin] = Field(min_length=1, max_length=30)
    latency_summary: Literal["p50_p95_p99_and_failures"]
    token_cost_summary: Literal["tokens_and_cost_per_successful_task"]
    failure_accounting: Literal["all_attempts_including_timeouts_and_abstentions"]


class ResearchCourseRecord(ClosedModel):
    opaque_course_id: str = Field(pattern=r"^course_[a-f0-9]{12}$")
    language: Literal["ru", "en"]


class ResearchCourseRegistry(ClosedModel):
    schema_version: Literal["research-course-registry.v1"]
    protocol_id: Literal["teacher_calibrated_multilingual_rag_v1"]
    labels_inspected: Literal[False]
    contains_outcomes: Literal[False]
    courses: list[ResearchCourseRecord] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_courses(self):
        values = [item.opaque_course_id for item in self.courses]
        if len(values) != len(set(values)):
            raise ValueError("duplicate opaque course IDs are not allowed")
        return self


class ResearchProtocol(ClosedModel):
    schema_version: Literal["research-protocol.v1"]
    protocol_id: Literal["teacher_calibrated_multilingual_rag_v1"]
    title: str = Field(min_length=20, max_length=300)
    status: Literal["frozen_awaiting_approvals_and_data"]
    frozen_on: date
    data_access_statement: Literal["no_real_pilot_outcomes_inspected"]
    research_question: str = Field(min_length=50, max_length=1500)
    claim: ResearchClaim
    conditions: list[Condition] = Field(min_length=3, max_length=10)
    endpoints: list[Endpoint] = Field(min_length=3, max_length=30)
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=20)
    datasets: list[DatasetRef] = Field(min_length=1, max_length=30)
    split_policy: SplitPolicy
    teacher_calibration: TeacherCalibrationPlan
    analysis_plan: AnalysisPlan
    ethics: EthicsPlan
    reproducibility: ReproducibilityPlan
    limitations: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_protocol_contract(self):
        condition_ids = _unique_ids(self.conditions, "condition")
        endpoint_ids = _unique_ids(self.endpoints, "endpoint")
        _unique_ids(self.hypotheses, "hypothesis")
        dataset_ids = _unique_ids(self.datasets, "dataset")
        approval_ids = _unique_ids(self.ethics.gates, "approval")
        pin_ids = _unique_ids(self.reproducibility.version_pins, "version pin")
        if not REQUIRED_CONDITIONS.issubset(condition_ids):
            raise ValueError(
                "non-agent, standard-RAG, and bounded-agent conditions are required"
            )
        required_kinds = {
            "canvas_search_baseline": "non_agent_baseline",
            "standard_course_rag": "rag_baseline",
            "bounded_role_aware_agent": "candidate",
        }
        actual_kinds = {item.id: item.kind for item in self.conditions}
        if any(
            actual_kinds.get(item_id) != kind
            for item_id, kind in required_kinds.items()
        ):
            raise ValueError(
                "registered baseline and candidate kinds cannot be changed"
            )
        if not REQUIRED_APPROVALS.issubset(approval_ids):
            raise ValueError(
                "required ethics and participant-protection gates are missing"
            )
        if not REQUIRED_VERSION_PINS.issubset(pin_ids):
            raise ValueError("required reproducibility version pins are missing")
        if not any(endpoint.primary for endpoint in self.endpoints):
            raise ValueError("at least one primary endpoint is required")
        for hypothesis in self.hypotheses:
            if hypothesis.endpoint_id not in endpoint_ids:
                raise ValueError("hypothesis references an unknown endpoint")
            if hypothesis.candidate_condition_id not in condition_ids:
                raise ValueError("hypothesis references an unknown candidate condition")
            if hypothesis.comparator_condition_id not in condition_ids:
                raise ValueError(
                    "hypothesis references an unknown comparator condition"
                )
            if hypothesis.candidate_condition_id == hypothesis.comparator_condition_id:
                raise ValueError("hypothesis conditions must differ")
        purposes = {
            dataset.purpose
            for dataset in self.datasets
            if dataset.evidence_class == "teacher_validated"
        }
        if not {"train", "development", "test"}.issubset(purposes):
            raise ValueError(
                "teacher-validated train/development/test datasets are required"
            )
        if self.ethics.collection_allowed and any(
            gate.required and gate.status != "approved" for gate in self.ethics.gates
        ):
            raise ValueError("collection cannot start before every required approval")
        if self.ethics.minors_in_initial_confirmatory_study:
            raise ValueError("minors require a separate approved protocol amendment")
        _validate_course_split_isolation(self.datasets)
        _validate_safe_values(self.model_dump(mode="json"))
        if not dataset_ids:
            raise ValueError("at least one dataset is required")
        return self


def _unique_ids(items: list[object], label: str) -> set[str]:
    values = [str(getattr(item, "id")) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} IDs are not allowed")
    return set(values)


def _validate_course_split_isolation(datasets: list[DatasetRef]) -> None:
    owners: dict[str, str] = {}
    for dataset in datasets:
        if dataset.purpose not in {"train", "development", "test"}:
            continue
        for course_id in dataset.opaque_course_ids:
            previous = owners.get(course_id)
            if previous is not None and previous != dataset.purpose:
                raise ValueError(
                    f"course-level split leakage between {previous} and {dataset.purpose}"
                )
            owners[course_id] = dataset.purpose


def _validate_safe_values(value: object, *, key: str | None = None) -> None:
    if key is not None and key.lower() in FORBIDDEN_KEYS:
        raise ValueError(f"unsafe research protocol field: {key}")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _validate_safe_values(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _validate_safe_values(child, key=key)
    elif isinstance(value, str):
        if EMAIL_PATTERN.search(value):
            raise ValueError("direct email identifiers are not allowed")
        if PHONE_PATTERN.search(value):
            raise ValueError("phone-shaped identifiers are not allowed")
        if DIRECT_ID_PATTERN.search(value):
            raise ValueError("direct LMS or participant identifiers are not allowed")
        if GRADE_PATTERN.search(value):
            raise ValueError("grade-shaped participant outcomes are not allowed")
        if LABELED_NAME_PATTERN.search(value):
            raise ValueError("person-name-shaped identifiers are not allowed")
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            raise ValueError("credential-shaped values are not allowed")


def load_research_protocol(path: Path) -> ResearchProtocol:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ResearchProtocol.model_validate(raw)


def canonical_protocol_bytes(protocol: ResearchProtocol) -> bytes:
    payload = protocol.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def protocol_sha256(protocol: ResearchProtocol) -> str:
    return hashlib.sha256(canonical_protocol_bytes(protocol)).hexdigest()


def course_registry_sha256(registry: ResearchCourseRegistry) -> str:
    payload = registry.model_dump(mode="json")
    payload["courses"] = sorted(
        payload["courses"], key=lambda item: item["opaque_course_id"]
    )
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def assign_blinded_course_splits(
    protocol: ResearchProtocol,
    registry: ResearchCourseRegistry,
) -> dict[str, object]:
    if registry.protocol_id != protocol.protocol_id:
        raise ValueError("course registry belongs to another protocol")
    by_language: dict[str, list[str]] = {"ru": [], "en": []}
    for course in registry.courses:
        by_language[course.language].append(course.opaque_course_id)
    sample_size = protocol.analysis_plan.sample_size
    if len(registry.courses) < sample_size.teacher_validated_courses:
        raise ValueError("course registry is below the frozen total sample-size floor")
    for language, course_ids in by_language.items():
        if len(course_ids) < sample_size.courses_per_language_minimum:
            raise ValueError(
                f"course registry is below the frozen {language} sample-size floor"
            )

    splits: dict[str, list[str]] = {
        "train": [],
        "development": [],
        "test": [],
    }
    policy = protocol.split_policy
    for language in ("ru", "en"):
        ordered = sorted(
            by_language[language],
            key=lambda course_id: hashlib.sha256(
                f"{policy.public_salt}:{course_id}".encode("utf-8")
            ).hexdigest(),
        )
        count = len(ordered)
        train_count = count * policy.train_percent // 100
        development_count = count * policy.development_percent // 100
        splits["train"].extend(ordered[:train_count])
        splits["development"].extend(
            ordered[train_count : train_count + development_count]
        )
        splits["test"].extend(ordered[train_count + development_count :])
    for values in splits.values():
        values.sort()
    owners: dict[str, str] = {}
    for split, course_ids in splits.items():
        for course_id in course_ids:
            if course_id in owners:
                raise ValueError("generated course split leakage")
            owners[course_id] = split
    if len(owners) != len(registry.courses):
        raise ValueError("generated split did not assign every course")
    language_by_course = {
        course.opaque_course_id: course.language for course in registry.courses
    }
    return {
        "schema_version": "research-course-split-manifest.v1",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol_sha256(protocol),
        "course_registry_sha256": course_registry_sha256(registry),
        "assignment": policy.assignment,
        "unit": policy.unit,
        "language_balance": policy.language_balance,
        "percentages": {
            "train": policy.train_percent,
            "development": policy.development_percent,
            "test": policy.test_percent,
        },
        "language_counts": {
            split: {
                language: sum(
                    language_by_course[course_id] == language
                    for course_id in course_ids
                )
                for language in ("ru", "en")
            }
            for split, course_ids in splits.items()
        },
        "splits": splits,
    }


def verify_committed_datasets(protocol: ResearchProtocol, repo_root: Path) -> None:
    resolved_root = repo_root.resolve()
    for dataset in protocol.datasets:
        if dataset.status != "committed":
            continue
        relative = Path(dataset.path or "")
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                f"dataset {dataset.id} path must stay inside the repository"
            )
        target = (resolved_root / relative).resolve()
        try:
            target.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"dataset {dataset.id} escapes the repository") from exc
        if not target.is_file():
            raise ValueError(f"dataset {dataset.id} file is missing")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != dataset.sha256:
            raise ValueError(f"dataset {dataset.id} SHA-256 mismatch")


def protocol_blockers(protocol: ResearchProtocol) -> list[str]:
    blockers: list[str] = []
    for gate in protocol.ethics.gates:
        if gate.required and gate.status != "approved":
            blockers.append(f"approval:{gate.id}")
    for pin in protocol.reproducibility.version_pins:
        if pin.status != "pinned":
            blockers.append(f"version:{pin.id}")
    for dataset in protocol.datasets:
        if dataset.evidence_class != "synthetic_regression" and (
            dataset.status != "committed"
            or dataset.sha256 is None
            or not dataset.opaque_course_ids
        ):
            blockers.append(f"dataset:{dataset.id}")
    if not protocol.ethics.collection_allowed:
        blockers.append("collection:disabled")
    return sorted(set(blockers))


def research_protocol_report(
    protocol: ResearchProtocol,
    *,
    repo_root: Path,
) -> dict[str, object]:
    verify_committed_datasets(protocol, repo_root)
    blockers = protocol_blockers(protocol)
    execution_ready = not blockers
    return {
        "schema_version": "research-protocol-report.v1",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol_sha256(protocol),
        "status": protocol.status,
        "execution_ready": execution_ready,
        "analysis_ready": execution_ready,
        "collection_allowed": protocol.ethics.collection_allowed,
        "blockers": blockers,
        "research_question": protocol.research_question,
        "currently_supported_claim": protocol.claim.currently_supported,
        "conditions": [item.model_dump(mode="json") for item in protocol.conditions],
        "hypotheses": [item.model_dump(mode="json") for item in protocol.hypotheses],
        "endpoints": [item.model_dump(mode="json") for item in protocol.endpoints],
        "primary_endpoints": [
            item.model_dump(mode="json") for item in protocol.endpoints if item.primary
        ],
        "datasets": [item.model_dump(mode="json") for item in protocol.datasets],
        "split_policy": protocol.split_policy.model_dump(mode="json"),
        "teacher_calibration": protocol.teacher_calibration.model_dump(mode="json"),
        "analysis_plan": protocol.analysis_plan.model_dump(mode="json"),
        "ethics": protocol.ethics.model_dump(mode="json"),
        "reproducibility": protocol.reproducibility.model_dump(mode="json"),
        "prohibited_claims": protocol.claim.prohibited,
        "limitations": protocol.limitations,
    }


def research_protocol_markdown(report: dict[str, object]) -> str:
    blockers = list(report["blockers"])
    conditions = list(report["conditions"])
    endpoints = list(report["primary_endpoints"])
    datasets = list(report["datasets"])
    limitations = list(report["limitations"])
    prohibited = list(report["prohibited_claims"])
    hypotheses = list(report["hypotheses"])
    analysis = dict(report["analysis_plan"])
    sample_size = dict(analysis["sample_size"])
    ethics = dict(report["ethics"])
    reproducibility = dict(report["reproducibility"])
    calibration = dict(report["teacher_calibration"])
    lines = [
        "# Frozen research protocol",
        "",
        f"- Protocol: `{report['protocol_id']}`",
        f"- SHA-256: `{report['protocol_sha256']}`",
        f"- Status: **{report['status']}**",
        f"- Execution ready: **{'yes' if report['execution_ready'] else 'no'}**",
        f"- Analysis ready: **{'yes' if report['analysis_ready'] else 'no'}**",
        f"- Participant collection allowed: **{'yes' if report['collection_allowed'] else 'no'}**",
        "",
        "## Research question",
        "",
        str(report["research_question"]),
        "",
        "## What is supported now",
        "",
        "Only a frozen, reproducible protocol exists. Current synthetic results are engineering regression evidence, not classroom-effectiveness evidence.",
        "",
        "## Blocking gates",
        "",
    ]
    lines.extend(f"- `{item}`" for item in blockers)
    lines.extend(["", "## Compared conditions", ""])
    lines.extend(
        f"- **{item['id']}** ({item['kind']}): {item['description']}"
        for item in conditions
    )
    lines.extend(["", "## Primary endpoints", ""])
    lines.extend(
        f"- **{item['id']}** — {item['metric']}: {item['estimand']}"
        for item in endpoints
    )
    lines.extend(["", "## Frozen hypotheses", ""])
    lines.extend(
        f"- **{item['id']}** ({item['endpoint_id']}): {item['statement']}"
        for item in hypotheses
    )
    lines.extend(
        [
            "",
            "## Teacher calibration",
            "",
            f"- Source: `{calibration['source']}`",
            f"- Locked-test rule: `{calibration['locked_test_rule']}`",
            f"- Adjudication: {calibration['adjudication']}",
            f"- Agreement: {calibration['agreement_metric']}",
            "- Tunable on development courses only:",
        ]
    )
    lines.extend(f"  - {item}" for item in calibration["tunable_components"])
    lines.extend(["", "## Dataset classes", ""])
    lines.extend(
        f"- **{item['id']}** — {item['evidence_class']} / {item['purpose']} / {item['status']}; confirmatory eligible: {str(item['confirmatory_eligible']).lower()}"
        for item in datasets
    )
    lines.extend(
        [
            "",
            "## Analysis plan",
            "",
            f"- Population: `{analysis['analysis_population']}`",
            f"- Multiplicity: `{analysis['confirmatory_family']}` using `{analysis['primary_multiplicity']}` at alpha {analysis['alpha']}",
            f"- Confidence intervals: `{analysis['confidence_interval']}`",
            f"- Stopping: `{analysis['stopping_rule']}`",
            f"- Language analysis: `{analysis['subgroup_policy']}`",
            f"- Missing data: {analysis['missing_data']}",
            f"- Instructor design: {analysis['instructor_design']}",
            f"- Safety gate: {analysis['safety_gate_policy']}",
            f"- Grounding gate: {analysis['grounding_gate_policy']}",
            "- Predeclared exclusions:",
        ]
    )
    lines.extend(f"  - {item}" for item in analysis["exclusions"])
    lines.extend(
        [
            f"- Sample-size floor: {sample_size['teacher_validated_courses']} teacher-validated courses, at least {sample_size['courses_per_language_minimum']} per language, at least {sample_size['locked_tasks_per_course_minimum']} locked tasks per course ({sample_size['supported_tasks_per_course_minimum']} supported and {sample_size['adversarial_tasks_per_course_minimum']} adversarial), and {sample_size['instructor_participants']} instructors.",
            f"- Power assumption: {sample_size['power']} power, alpha {sample_size['alpha']}, detectable paired standardized instructor effect {sample_size['detectable_standardized_effect']}, task-success difference {sample_size['detectable_task_completion_difference']}, and Recall@K difference {sample_size['detectable_retrieval_recall_difference']} from baseline {sample_size['retrieval_baseline_rate']} with course ICC {sample_size['assumed_course_icc']}, subject to the pinned clustered power artifact before registry lock.",
            f"- Rationale: {sample_size['rationale']}",
            "",
            "## Ethics and privacy gates",
            "",
            f"- Collection allowed: **{'yes' if ethics['collection_allowed'] else 'no'}**",
            f"- Minors in initial confirmatory study: **{'yes' if ethics['minors_in_initial_confirmatory_study'] else 'no'}**",
            f"- Raw messages collected: **{'yes' if ethics['raw_message_collection'] else 'no'}**",
            f"- Personnel or student ranking: **{'yes' if ethics['personnel_or_student_ranking'] else 'no'}**",
            f"- Retention: {ethics['retention_days']} days after approved collection.",
            "- Approval gates:",
        ]
    )
    lines.extend(
        f"  - `{item['id']}` — {item['status']}: {item['rule']}"
        for item in ethics["gates"]
    )
    lines.extend(["- Data minimization:"])
    lines.extend(f"  - {item}" for item in ethics["data_minimization"])
    lines.extend(
        [
            f"- Adverse-event rule: {ethics['adverse_event_rule']}",
            "",
            "## Reproducibility pins",
            "",
        ]
    )
    lines.extend(
        f"- `{item['id']}` — {item['status']}: `{item['value']}`"
        for item in reproducibility["version_pins"]
    )
    lines.extend(["", "Required fields for every future run:", ""])
    lines.extend(f"- `{item}`" for item in reproducibility["required_run_fields"])
    lines.extend(["", "## Claims this protocol cannot support yet", ""])
    lines.extend(f"- {item}" for item in prohibited)
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in limitations)
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "PROTOCOL_ID",
    "PROTOCOL_SCHEMA_VERSION",
    "ResearchProtocol",
    "ResearchCourseRegistry",
    "assign_blinded_course_splits",
    "canonical_protocol_bytes",
    "course_registry_sha256",
    "load_research_protocol",
    "protocol_blockers",
    "protocol_sha256",
    "research_protocol_markdown",
    "research_protocol_report",
    "verify_committed_datasets",
]
