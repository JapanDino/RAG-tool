from __future__ import annotations

import os
from typing import Any


REVIEW_NEEDED_RATIONALES = {"insufficient-signal", "low-confidence"}
DEFAULT_REVIEW_UNCERTAINTY = float(os.getenv("BLOOM_REVIEW_UNCERTAINTY", "0.85"))


def prediction_uncertainty(prob_vector: list[float]) -> float:
    if not prob_vector or len(prob_vector) < 2:
        return 1.0
    probs = sorted((float(x) for x in prob_vector), reverse=True)
    return 1.0 - (probs[0] - probs[1])


def assess_prediction_review(
    top_levels: list[str] | None,
    rationale: str | None,
    prob_vector: list[float] | None,
    uncertainty_threshold: float = DEFAULT_REVIEW_UNCERTAINTY,
) -> dict[str, Any]:
    levels = list(top_levels or [])
    uncertainty = prediction_uncertainty(list(prob_vector or []))
    reasons: list[str] = []

    if not levels:
        reasons.append("no-top-levels")
    if rationale in REVIEW_NEEDED_RATIONALES:
        reasons.append(str(rationale))
    if levels and uncertainty >= uncertainty_threshold:
        reasons.append("high-uncertainty")

    status = "needs_review" if reasons else "scorable"
    return {
        "status": status,
        "uncertainty": round(uncertainty, 4),
        "reasons": reasons,
    }
