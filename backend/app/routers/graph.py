from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import KnowledgeNode, KnowledgeEdge, Job, JobType, JobStatus
from ..schemas.schemas import GraphOut, GraphNodeOut, GraphEdgeOut, GraphRebuildIn, GraphRebuildOut
from ..tasks.queue import enqueue_or_mark

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/rebuild", response_model=GraphRebuildOut)
def rebuild_graph(payload: GraphRebuildIn, db: Session = Depends(get_db)):
    job = Job(
        type=JobType.graph,
        status=JobStatus.queued,
        payload={
            "dataset_id": payload.dataset_id,
            "embedding_model": payload.embedding_model,
            "top_k": payload.top_k,
            "min_score": payload.min_score,
            "max_edges": payload.max_edges,
            "include_cooccurrence": payload.include_cooccurrence,
            "limit_nodes": payload.limit_nodes,
            "co_window": payload.co_window,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_or_mark(db, job)
    return GraphRebuildOut(job_id=job.id)


def _add_edge(edge_map: dict[tuple[int, int, str], float], a: int, b: int, weight: float, method: str):
    if a == b:
        return
    key = (min(a, b), max(a, b), method)
    current = edge_map.get(key)
    if current is None or weight > current:
        edge_map[key] = weight


def _load_persisted_edges(
    db: Session,
    *,
    dataset_id: int | None,
    node_ids: list[int],
    node_models: set[str],
    embedding_model: str | None,
    include_cooccurrence: bool,
    min_score: float,
    max_edges: int,
) -> list[GraphEdgeOut]:
    if dataset_id is None or not node_ids:
        return []

    method_filters = []
    if embedding_model:
        method_filters.append(KnowledgeEdge.method == f"similarity|{embedding_model}")
    elif node_models:
        for model_name in sorted(node_models):
            method_filters.append(KnowledgeEdge.method == f"similarity|{model_name}")
    else:
        method_filters.append(KnowledgeEdge.method.like("similarity|%"))

    if include_cooccurrence:
        method_filters.append(KnowledgeEdge.method == "co_occurrence_window")

    if not method_filters:
        return []

    rows = (
        db.query(KnowledgeEdge)
        .filter(
            KnowledgeEdge.dataset_id == dataset_id,
            KnowledgeEdge.from_node_id.in_(node_ids),
            KnowledgeEdge.to_node_id.in_(node_ids),
            or_(*method_filters),
        )
        .order_by(KnowledgeEdge.weight.desc(), KnowledgeEdge.id.asc())
        .limit(max_edges * 5)
        .all()
    )

    edge_items: list[GraphEdgeOut] = []
    for row in rows:
        if row.method.startswith("similarity|") and float(row.weight) < min_score:
            continue
        edge_items.append(
            GraphEdgeOut(
                from_id=int(row.from_node_id),
                to_id=int(row.to_node_id),
                weight=float(row.weight),
            )
        )
        if len(edge_items) >= max_edges:
            break
    return edge_items


@router.get("", response_model=GraphOut)
def get_graph(
    dataset_id: int | None = None,
    document_id: int | None = None,
    embedding_model: str | None = None,
    top_k: int = Query(5, ge=1, le=50),
    min_score: float = Query(0.2, ge=0.0, le=1.0),
    max_edges: int = Query(200, ge=1, le=5000),
    include_cooccurrence: bool = True,
    limit_nodes: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    filters = ["kn.vec IS NOT NULL"]
    params: dict[str, object] = {"limit": limit_nodes}
    if dataset_id is not None:
        filters.append("kn.dataset_id = :ds")
        params["ds"] = dataset_id
    if document_id is not None:
        filters.append("kn.document_id = :doc")
        params["doc"] = document_id
    if embedding_model is not None:
        filters.append("kn.embedding_model = :em")
        params["em"] = embedding_model
    where_clause = " AND ".join(filters)
    ids_sql = f"""
        SELECT kn.id
        FROM knowledge_nodes kn
        WHERE {where_clause}
        ORDER BY kn.id ASC
        LIMIT :limit
    """
    node_ids = [row[0] for row in db.execute(text(ids_sql), params).all()]
    if node_ids:
        nodes = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.id.in_(node_ids))
            .order_by(KnowledgeNode.id.asc())
            .all()
        )
    else:
        nodes = []
    node_index = {n.id: n for n in nodes}

    persisted_edges = _load_persisted_edges(
        db,
        dataset_id=dataset_id,
        node_ids=node_ids,
        node_models={str(n.embedding_model) for n in nodes if n.embedding_model},
        embedding_model=embedding_model,
        include_cooccurrence=include_cooccurrence,
        min_score=min_score,
        max_edges=max_edges,
    )
    if persisted_edges:
        node_items = [
            GraphNodeOut(
                id=n.id,
                title=n.title,
                context_text=n.context_text,
                prob_vector=n.prob_vector,
                top_levels=n.top_levels,
            )
            for n in nodes
        ]
        return GraphOut(nodes=node_items, edges=persisted_edges)

    edges: dict[tuple[int, int, str], float] = {}

    if node_ids:
        # Single batched query using LATERAL JOIN — pgvector finds top_k neighbours
        # for every node in one round-trip instead of N separate queries.
        extra_filters: list[str] = ["b.id != a.id", "b.vec IS NOT NULL"]
        params_batch: dict[str, object] = {
            "ids": node_ids,
            "top_k": top_k,
            "min_score": min_score,
            "max_edges": max_edges,
        }
        if dataset_id is not None:
            extra_filters.append("b.dataset_id = :ds")
            params_batch["ds"] = dataset_id
        if document_id is not None:
            extra_filters.append("b.document_id = :doc")
            params_batch["doc"] = document_id
        if embedding_model is not None:
            extra_filters.append("b.embedding_model = :em")
            params_batch["em"] = embedding_model
        neighbour_where = " AND ".join(extra_filters)

        batch_sql = f"""
            SELECT a.id AS from_id, nb.to_id, 1.0 - nb.dist AS score
            FROM knowledge_nodes a
            CROSS JOIN LATERAL (
                SELECT b.id AS to_id, (a.vec <=> b.vec) AS dist
                FROM knowledge_nodes b
                WHERE {neighbour_where}
                  AND b.id = ANY(:ids)
                ORDER BY a.vec <=> b.vec ASC
                LIMIT :top_k
            ) nb
            WHERE a.id = ANY(:ids)
              AND a.vec IS NOT NULL
              AND 1.0 - nb.dist >= :min_score
            ORDER BY score DESC
            LIMIT :max_edges
        """
        rows = db.execute(text(batch_sql), params_batch).mappings().all()
        for row in rows:
            _add_edge(edges, int(row["from_id"]), int(row["to_id"]), round(float(row["score"]), 4), "similarity")
            if len(edges) >= max_edges:
                break

    if include_cooccurrence and len(edges) < max_edges:
        by_doc: dict[int, list[int]] = defaultdict(list)
        for node in nodes:
            if node.document_id is not None:
                by_doc[int(node.document_id)].append(node.id)
        for doc_nodes in by_doc.values():
            doc_nodes.sort()
            for i in range(len(doc_nodes) - 1):
                _add_edge(edges, doc_nodes[i], doc_nodes[i + 1], 0.5, "co_occurrence")
                if len(edges) >= max_edges:
                    break
            if len(edges) >= max_edges:
                break

    edge_items = [
        GraphEdgeOut(from_id=a, to_id=b, weight=weight)
        for (a, b, _method), weight in list(edges.items())[:max_edges]
        if a in node_index and b in node_index
    ]
    node_items = [
        GraphNodeOut(
            id=n.id,
            title=n.title,
            context_text=n.context_text,
            prob_vector=n.prob_vector,
            top_levels=n.top_levels,
        )
        for n in nodes
    ]
    return GraphOut(nodes=node_items, edges=edge_items)
