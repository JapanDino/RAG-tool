from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import Dataset, KnowledgeNode, NodeLabel, NodeLabelRevision
from ..schemas.schemas import LabelQueueOut, LabelQueueItem, NodeLabelRevisionOut, NodeLabelsIn, NodeLabelsOut
from ..utils.review_status import assess_prediction_review


router = APIRouter(prefix="/datasets", tags=["labeling"])


def _coerce_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


@router.get("/{dataset_id}/labeling/queue", response_model=LabelQueueOut)
def labeling_queue(
    dataset_id: int,
    annotator: str = "default",
    embedding_model: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    review_status: str = Query("all", pattern="^(all|needs_review|scorable)$"),
    include_labeled: bool = False,
    db: Session = Depends(get_db),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    # Fetch all matching candidates so the queue can be ranked globally by
    # uncertainty/review-need instead of whichever records happen to appear in
    # the first limited SQL page.
    where = ["kn.dataset_id = :ds"]
    params: dict[str, Any] = {"ds": dataset_id, "ann": annotator}
    if embedding_model:
        where.append("kn.embedding_model = :em")
        params["em"] = embedding_model
    if not include_labeled:
        where.append("nl.id IS NULL")

    sql = f"""
        SELECT kn.id, kn.title, kn.context_text, kn.prob_vector, kn.top_levels, kn.model_info,
               nl.labels as labels
        FROM knowledge_nodes kn
        LEFT JOIN node_labels nl
          ON nl.node_id = kn.id AND nl.annotator = :ann
        WHERE {" AND ".join(where)}
        ORDER BY kn.id ASC
    """
    rows = db.execute(text(sql), params).mappings().all()

    items: list[LabelQueueItem] = []
    scorable_total = 0
    needs_review_total = 0
    for r in rows:
        prob_vector = _coerce_json_field(r.get("prob_vector")) or []
        top_levels = _coerce_json_field(r.get("top_levels")) or []
        mi = _coerce_json_field(r.get("model_info")) or {}
        freq = mi.get("frequency") if isinstance(mi, dict) else None
        rationale = mi.get("rationale") if isinstance(mi, dict) else None
        labels = _coerce_json_field(r.get("labels"))
        labeled = labels is not None
        review = assess_prediction_review(
            list(top_levels),
            rationale,
            list(prob_vector),
        )
        if review["status"] == "needs_review":
            needs_review_total += 1
        else:
            scorable_total += 1
        if review_status != "all" and review["status"] != review_status:
            continue
        items.append(
            LabelQueueItem(
                id=int(r["id"]),
                title=str(r["title"]),
                context_text=str(r["context_text"]),
                prob_vector=list(prob_vector),
                top_levels=list(top_levels),
                frequency=freq,
                rationale=rationale,
                uncertainty=float(review["uncertainty"]),
                review_status=str(review["status"]),
                review_reasons=list(review["reasons"]),
                labeled=labeled,
                labels=list(labels) if labels is not None else None,
            )
        )

    # Prioritize nodes that need human review first, then by uncertainty.
    items.sort(
        key=lambda x: (
            0 if x.review_status == "needs_review" else 1,
            -float(x.uncertainty),
            x.id,
        )
    )
    items = items[:limit]

    # total/labeled stats
    total_q = db.query(KnowledgeNode).filter(KnowledgeNode.dataset_id == dataset_id)
    if embedding_model:
        total_q = total_q.filter(KnowledgeNode.embedding_model == embedding_model)
    total = total_q.count()
    labeled_q = (
        db.query(NodeLabel)
        .join(KnowledgeNode, NodeLabel.node_id == KnowledgeNode.id)
        .filter(KnowledgeNode.dataset_id == dataset_id, NodeLabel.annotator == annotator)
    )
    if embedding_model:
        labeled_q = labeled_q.filter(KnowledgeNode.embedding_model == embedding_model)
    labeled_total = labeled_q.count()

    return LabelQueueOut(
        total=total,
        labeled=labeled_total,
        scorable=scorable_total,
        needs_review=needs_review_total,
        items=items,
    )


@router.get("/{dataset_id}/labeling/export")
def export_labels(
    dataset_id: int,
    annotator: str = "default",
    embedding_model: str | None = None,
    review_status: str = Query("all", pattern="^(all|needs_review|scorable)$"),
    fmt: str = Query("jsonl", pattern="^(jsonl)$"),
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
    rows = q.order_by(NodeLabel.id.asc()).all()
    lines = []
    for nl, kn in rows:
        model_info = kn.model_info if isinstance(kn.model_info, dict) else {}
        review = assess_prediction_review(
            list(kn.top_levels or []),
            model_info.get("rationale"),
            list(kn.prob_vector or []),
        )
        if review_status != "all" and review["status"] != review_status:
            continue
        lines.append(
            json.dumps(
                {
                    "node_id": kn.id,
                    "title": kn.title,
                    "context_text": kn.context_text,
                    "labels": nl.labels,
                    "prob_vector": kn.prob_vector,
                    "top_levels": kn.top_levels,
                    "embedding_model": kn.embedding_model,
                    "prediction_review_status": review["status"],
                    "prediction_review_reasons": review["reasons"],
                    "prediction_uncertainty": review["uncertainty"],
                },
                ensure_ascii=False,
            )
        )
    body = "\n".join(lines) + ("\n" if lines else "")
    return Response(content=body, media_type="application/jsonl")


# ── Per-node label endpoints (prefix /nodes, registered via main.py as separate router) ─

nodes_router = APIRouter(prefix="/nodes", tags=["labeling"])


def _append_label_revision(db: Session, nl: NodeLabel) -> None:
    db.add(
        NodeLabelRevision(
            node_label_id=nl.id,
            node_id=nl.node_id,
            labels=list(nl.labels or []),
            annotator=nl.annotator,
            source=nl.source,
            version=nl.version or 1,
        )
    )


@nodes_router.post("/{node_id}/labels", response_model=NodeLabelsOut)
@nodes_router.put("/{node_id}/labels", response_model=NodeLabelsOut)
def set_node_labels(
    node_id: int,
    payload: NodeLabelsIn,
    db: Session = Depends(get_db),
):
    node = db.get(KnowledgeNode, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    nl = (
        db.query(NodeLabel)
        .filter(NodeLabel.node_id == node_id, NodeLabel.annotator == payload.annotator)
        .first()
    )
    if nl:
        new_labels = list(payload.labels)
        if list(nl.labels or []) != new_labels:
            nl.labels = new_labels
            nl.version = (nl.version or 1) + 1
            nl.updated_at = datetime.now(timezone.utc)
            db.flush()
            _append_label_revision(db, nl)
    else:
        nl = NodeLabel(
            node_id=node_id,
            labels=list(payload.labels),
            annotator=payload.annotator,
            source="human",
            version=1,
        )
        db.add(nl)
        db.flush()
        _append_label_revision(db, nl)
    db.commit()
    db.refresh(nl)
    return NodeLabelsOut(
        node_id=node_id,
        annotator=nl.annotator,
        labels=nl.labels,
        version=nl.version or 1,
        created_at=str(nl.created_at),
        updated_at=str(nl.updated_at),
    )


@nodes_router.get("/{node_id}/labels", response_model=NodeLabelsOut)
def get_node_labels(
    node_id: int,
    annotator: str = "default",
    db: Session = Depends(get_db),
):
    node = db.get(KnowledgeNode, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    nl = (
        db.query(NodeLabel)
        .filter(NodeLabel.node_id == node_id, NodeLabel.annotator == annotator)
        .first()
    )
    if not nl:
        raise HTTPException(404, "no labels found for this node/annotator")
    return NodeLabelsOut(
        node_id=node_id,
        annotator=nl.annotator,
        labels=nl.labels,
        version=nl.version or 1,
        created_at=str(nl.created_at),
        updated_at=str(nl.updated_at),
    )


@nodes_router.get("/{node_id}/labels/history", response_model=list[NodeLabelRevisionOut])
def get_node_label_history(
    node_id: int,
    annotator: str = "default",
    db: Session = Depends(get_db),
):
    node = db.get(KnowledgeNode, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    rows = (
        db.query(NodeLabelRevision)
        .filter(
            NodeLabelRevision.node_id == node_id,
            NodeLabelRevision.annotator == annotator,
        )
        .order_by(NodeLabelRevision.version.asc(), NodeLabelRevision.id.asc())
        .all()
    )
    return [
        NodeLabelRevisionOut(
            id=row.id,
            node_id=row.node_id,
            annotator=row.annotator,
            labels=row.labels,
            version=row.version,
            source=row.source,
            created_at=str(row.created_at),
        )
        for row in rows
    ]
