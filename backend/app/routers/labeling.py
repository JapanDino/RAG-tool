from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import Dataset, KnowledgeNode, NodeLabel
from ..schemas.schemas import LabelQueueOut, LabelQueueItem, NodeLabelsIn, NodeLabelsOut
from ..services.embedding_provider import current_embedding_model


router = APIRouter(prefix="/datasets", tags=["labeling"])


def _uncertainty(prob_vector: list[float]) -> float:
    if not prob_vector or len(prob_vector) < 2:
        return 1.0
    probs = sorted([float(x) for x in prob_vector], reverse=True)
    return 1.0 - (probs[0] - probs[1])


@router.get("/{dataset_id}/labeling/queue", response_model=LabelQueueOut)
def labeling_queue(
    dataset_id: int,
    annotator: str = "default",
    embedding_model: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    include_labeled: bool = False,
    db: Session = Depends(get_db),
):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    em = embedding_model or current_embedding_model()

    # Fetch nodes and (optional) existing labels for annotator.
    # Left join: if include_labeled=false, we filter out labeled in SQL.
    where = ["kn.dataset_id = :ds"]
    params: dict[str, Any] = {"ds": dataset_id, "ann": annotator, "limit": limit * 5}
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
        LIMIT :limit
    """
    rows = db.execute(text(sql), params).mappings().all()

    items: list[LabelQueueItem] = []
    labeled_cnt = 0
    for r in rows:
        mi = r.get("model_info") or {}
        freq = mi.get("frequency") if isinstance(mi, dict) else None
        rationale = mi.get("rationale") if isinstance(mi, dict) else None
        labels = r.get("labels")
        labeled = labels is not None
        if labeled:
            labeled_cnt += 1
        items.append(
            LabelQueueItem(
                id=int(r["id"]),
                title=str(r["title"]),
                context_text=str(r["context_text"]),
                prob_vector=list(r.get("prob_vector") or []),
                top_levels=list(r.get("top_levels") or []),
                frequency=freq,
                rationale=rationale,
                labeled=labeled,
                labels=list(labels) if labels is not None else None,
            )
        )

    # Prioritize by uncertainty to speed up building a good dataset.
    items.sort(key=lambda x: _uncertainty(x.prob_vector), reverse=True)
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

    return LabelQueueOut(total=total, labeled=labeled_total, items=items)


@router.get("/{dataset_id}/labeling/export")
def export_labels(
    dataset_id: int,
    annotator: str = "default",
    embedding_model: str | None = None,
    fmt: str = Query("jsonl", pattern="^(jsonl)$"),
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
        .order_by(NodeLabel.id.asc())
        .all()
    )
    lines = []
    for nl, kn in rows:
        lines.append(
            json.dumps(
                {
                    "node_id": kn.id,
                    "title": kn.title,
                    "context_text": kn.context_text,
                    "labels": nl.labels,
                    "prob_vector": kn.prob_vector,
                    "top_levels": kn.top_levels,
                },
                ensure_ascii=False,
            )
        )
    body = "\n".join(lines) + ("\n" if lines else "")
    return Response(content=body, media_type="application/jsonl")


# ── Per-node label endpoints (prefix /nodes, registered via main.py as separate router) ─

nodes_router = APIRouter(prefix="/nodes", tags=["labeling"])


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
        nl.labels = list(payload.labels)
    else:
        nl = NodeLabel(node_id=node_id, labels=list(payload.labels), annotator=payload.annotator, source="human")
        db.add(nl)
    db.commit()
    db.refresh(nl)
    return NodeLabelsOut(
        node_id=node_id,
        annotator=nl.annotator,
        labels=nl.labels,
        created_at=str(nl.created_at),
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
        created_at=str(nl.created_at),
    )

