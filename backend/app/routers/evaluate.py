from __future__ import annotations

from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import KnowledgeNode, NodeLabel
from ..utils.bloom import LEVEL_ORDER
from ..utils.review_status import assess_prediction_review
from ..services.bloom_multilabel import classify_bloom_multilabel


router = APIRouter(prefix="/evaluate", tags=["evaluate"])


def _vectorize(labels: Iterable[str]) -> list[int]:
    s = {str(x) for x in labels}
    return [1 if lvl in s else 0 for lvl in LEVEL_ORDER]


def _hamming_loss(y_true: list[list[int]], y_pred: list[list[int]]) -> float:
    if not y_true:
        return 0.0
    total = 0
    for t, p in zip(y_true, y_pred):
        total += sum(1 for tv, pv in zip(t, p) if tv != pv)
    return total / (len(y_true) * len(LEVEL_ORDER))


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
    for idx in range(len(LEVEL_ORDER)):
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
    return sum(f1s) / len(f1s) if f1s else 0.0


def _per_level(y_true: list[list[int]], y_pred: list[list[int]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for idx, lvl in enumerate(LEVEL_ORDER):
        tp = fp = fn = 0
        for t, p in zip(y_true, y_pred):
            tv, pv = t[idx], p[idx]
            if tv == 1 and pv == 1:
                tp += 1
            elif tv == 0 and pv == 1:
                fp += 1
            elif tv == 1 and pv == 0:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        denom = (2 * tp + fp + fn)
        f1 = (2 * tp / denom) if denom else 0.0
        out[lvl] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": float(tp),
            "fp": float(fp),
            "fn": float(fn),
        }
    return out


@router.get("/metrics")
@router.get("/multilabel")
def evaluate_multilabel(
    dataset_id: int = Query(..., ge=1),
    annotator: str = "default",
    embedding_model: str | None = None,
    min_prob: float = 0.2,
    max_levels: int = 2,
    prediction_source: str = Query(
        "recompute",
        pattern="^(recompute|stored|auto)$",
    ),
    evaluation_scope: str = Query(
        "all",
        pattern="^(all|scorable_only|needs_review_only)$",
    ),
    db: Session = Depends(get_db),
):
    q = (
        db.query(NodeLabel, KnowledgeNode)
        .join(KnowledgeNode, NodeLabel.node_id == KnowledgeNode.id)
        .filter(
            KnowledgeNode.dataset_id == dataset_id,
            NodeLabel.annotator == annotator,
        )
    )
    if embedding_model:
        q = q.filter(KnowledgeNode.embedding_model == embedding_model)
    rows = q.all()
    if not rows:
        raise HTTPException(404, "no labeled nodes found")

    y_true: list[list[int]] = []
    y_pred: list[list[int]] = []
    used_stored_predictions = 0
    used_recomputed_predictions = 0
    considered_predictions = 0
    review_needed_predictions = 0
    scorable_predictions = 0
    skipped_predictions = 0

    for nl, kn in rows:
        if prediction_source == "stored":
            pred_levels = list(kn.top_levels or [])
            pred_rationale = ((kn.model_info or {}) if isinstance(kn.model_info, dict) else {}).get("rationale")
            pred_prob_vector = list(kn.prob_vector or [])
            used_stored_predictions += 1
        elif prediction_source == "auto" and kn.top_levels:
            pred_levels = list(kn.top_levels or [])
            pred_rationale = ((kn.model_info or {}) if isinstance(kn.model_info, dict) else {}).get("rationale")
            pred_prob_vector = list(kn.prob_vector or [])
            used_stored_predictions += 1
        else:
            text = f"{kn.title}. {kn.context_text}".strip()
            pred = classify_bloom_multilabel(text, min_prob=min_prob, max_levels=max_levels)
            pred_levels = list(pred.get("top_levels") or [])
            pred_rationale = pred.get("rationale")
            pred_prob_vector = list(pred.get("prob_vector") or [])
            used_recomputed_predictions += 1

        review = assess_prediction_review(pred_levels, pred_rationale, pred_prob_vector)
        considered_predictions += 1
        if review["status"] == "needs_review":
            review_needed_predictions += 1
        else:
            scorable_predictions += 1

        if evaluation_scope == "scorable_only" and review["status"] != "scorable":
            skipped_predictions += 1
            continue
        if evaluation_scope == "needs_review_only" and review["status"] != "needs_review":
            skipped_predictions += 1
            continue

        # An explicit stored-only evaluation should surface missing cached
        # predictions as empty predictions instead of silently recomputing them.
        y_true.append(_vectorize(nl.labels or []))
        y_pred.append(_vectorize(pred_levels))

    report: dict[str, Any] = {
        "samples": len(y_true),
        "samples_considered": considered_predictions,
        "hamming_loss": round(_hamming_loss(y_true, y_pred), 4),
        "f1_micro": round(_f1_micro(y_true, y_pred), 4),
        "f1_macro": round(_f1_macro(y_true, y_pred), 4),
        "per_level": _per_level(y_true, y_pred),
        "min_prob": min_prob,
        "max_levels": max_levels,
        "embedding_model": embedding_model or "all",
        "annotator": annotator,
        "prediction_source_requested": prediction_source,
        "evaluation_scope_requested": evaluation_scope,
        "evaluation_scope": evaluation_scope,
        "prediction_source": (
            "stored_top_levels"
            if used_recomputed_predictions == 0
            else "current_classifier"
            if used_stored_predictions == 0
            else "mixed"
        ),
        "stored_predictions": used_stored_predictions,
        "recomputed_predictions": used_recomputed_predictions,
        "review_needed_predictions": review_needed_predictions,
        "scorable_predictions": scorable_predictions,
        "skipped_predictions": skipped_predictions,
        "review_needed_rate": round(
            (review_needed_predictions / considered_predictions) if considered_predictions else 0.0,
            4,
        ),
    }
    return report
