from __future__ import annotations

from typing import Any, Optional, Tuple

from ..schemas.llm import LLMAnnotation, ValidationError


def validate_score_range(score: float) -> bool:
    return 0.0 <= score <= 1.0


def validate_rationale_length(rationale: str, min_len: int = 1, max_len: int = 4000) -> bool:
    return min_len <= len(rationale) <= max_len


def validate_label_length(label: str, min_len: int = 1, max_len: int = 200) -> bool:
    return min_len <= len(label) <= max_len


def validate_annotation(annotation: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    try:
        obj = LLMAnnotation(**annotation)
    except ValidationError as exc:
        return False, str(exc)

    if not validate_score_range(obj.score):
        return False, "score out of range"
    if not validate_label_length(obj.label):
        return False, "label length out of range"
    if not validate_rationale_length(obj.rationale):
        return False, "rationale length out of range"

    return True, None


__all__ = [
    "validate_annotation",
    "validate_score_range",
    "validate_rationale_length",
    "validate_label_length",
]

