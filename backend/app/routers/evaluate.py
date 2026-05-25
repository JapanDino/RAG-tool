from __future__ import annotations

from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import KnowledgeNode, NodeLabel
from ..utils.bloom import LEVEL_ORDER
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


def _cohen_kappa(y_true: list[list[int]], y_pred: list[list[int]]) -> float:
    """Multi-label Cohen's κ — macro-averaged over Bloom levels.

    For each label independently computes the standard binary Cohen's κ:
        κ = (p_o - p_e) / (1 - p_e)
    where ``p_o`` is observed agreement and ``p_e`` is expected agreement
    assuming independence.  Returns the unweighted macro average across all
    labels defined in ``LEVEL_ORDER``.  Returns 0.0 when there are no samples
    or when expected agreement is 1.0 for every label.
    """
    if not y_true:
        return 0.0
    n = len(y_true)
    kappas: list[float] = []
    for idx in range(len(LEVEL_ORDER)):
        t_col = [row[idx] for row in y_true]
        p_col = [row[idx] for row in y_pred]

        p_o = sum(1 for tv, pv in zip(t_col, p_col) if tv == pv) / n

        # marginal proportions for the positive class
        prev_t = sum(t_col) / n
        prev_p = sum(p_col) / n

        # expected agreement: both agree on 1 + both agree on 0
        p_e = prev_t * prev_p + (1 - prev_t) * (1 - prev_p)

        if p_e >= 1.0:
            kappas.append(1.0 if p_o >= 1.0 else 0.0)
        else:
            kappas.append((p_o - p_e) / (1 - p_e))

    return sum(kappas) / len(kappas) if kappas else 0.0


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
    expert_only: bool = False,
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
    if expert_only:
        q = q.filter(NodeLabel.is_expert.is_(True))
    rows = q.all()
    if not rows:
        raise HTTPException(404, "no labeled nodes found")

    y_true: list[list[int]] = []
    y_pred: list[list[int]] = []
    used_stored_predictions = 0
    used_recomputed_predictions = 0

    for nl, kn in rows:
        y_true.append(_vectorize(nl.labels or []))
        if kn.top_levels:
            y_pred.append(_vectorize(kn.top_levels))
            used_stored_predictions += 1
        else:
            text = f"{kn.title}. {kn.context_text}".strip()
            pred = classify_bloom_multilabel(text, min_prob=min_prob, max_levels=max_levels)
            y_pred.append(_vectorize(pred.get("top_levels") or []))
            used_recomputed_predictions += 1

    report: dict[str, Any] = {
        "samples": len(y_true),
        "hamming_loss": round(_hamming_loss(y_true, y_pred), 4),
        "f1_micro": round(_f1_micro(y_true, y_pred), 4),
        "f1_macro": round(_f1_macro(y_true, y_pred), 4),
        "cohen_kappa": round(_cohen_kappa(y_true, y_pred), 4),
        "per_level": _per_level(y_true, y_pred),
        "min_prob": min_prob,
        "max_levels": max_levels,
        "embedding_model": embedding_model or "all",
        "annotator": annotator,
        "expert_only": expert_only,
        "prediction_source": (
            "stored_top_levels"
            if used_recomputed_predictions == 0
            else "mixed"
        ),
        "stored_predictions": used_stored_predictions,
        "recomputed_predictions": used_recomputed_predictions,
    }
    return report
