from __future__ import annotations

from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import KnowledgeNode, NodeLabel
from ..services.embedding_provider import current_embedding_model
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


@router.get("/multilabel")
def evaluate_multilabel(
    dataset_id: int = Query(..., ge=1),
    annotator: str = "default",
    embedding_model: str | None = None,
    min_prob: float = 0.2,
    max_levels: int = 2,
    db: Session = Depends(get_db),
):
    em = embedding_model or current_embedding_model()

    rows = (
        db.query(NodeLabel, KnowledgeNode)
        .join(KnowledgeNode, NodeLabel.node_id == KnowledgeNode.id)
        .filter(
            KnowledgeNode.dataset_id == dataset_id,
            KnowledgeNode.embedding_model == em,
            NodeLabel.annotator == annotator,
        )
        .all()
    )
    if not rows:
        raise HTTPException(404, "no labeled nodes found")

    y_true: list[list[int]] = []
    y_pred: list[list[int]] = []

    for nl, kn in rows:
        text = f"{kn.title}. {kn.context_text}".strip()
        pred = classify_bloom_multilabel(text, min_prob=min_prob, max_levels=max_levels)
        y_true.append(_vectorize(nl.labels or []))
        y_pred.append(_vectorize(pred.get("top_levels") or []))

    report: dict[str, Any] = {
        "samples": len(y_true),
        "hamming_loss": round(_hamming_loss(y_true, y_pred), 4),
        "f1_micro": round(_f1_micro(y_true, y_pred), 4),
        "f1_macro": round(_f1_macro(y_true, y_pred), 4),
        "per_level": _per_level(y_true, y_pred),
        "min_prob": min_prob,
        "max_levels": max_levels,
        "embedding_model": em,
        "annotator": annotator,
    }
    return report
