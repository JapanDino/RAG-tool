from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import KnowledgeNode
from ..schemas.schemas import GraphOut, GraphNodeOut, GraphEdgeOut

router = APIRouter(prefix="/graph", tags=["graph"])


def _add_edge(edge_map: dict[tuple[int, int, str], float], a: int, b: int, weight: float, method: str):
    if a == b:
        return
    key = (min(a, b), max(a, b), method)
    current = edge_map.get(key)
    if current is None or weight > current:
        edge_map[key] = weight


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

    edges: dict[tuple[int, int, str], float] = {}

    if node_ids:
        filters = ["kn2.id != :id", "kn2.vec IS NOT NULL"]
        params_base: dict[str, object] = {"k": top_k, "min_score": min_score}
        if dataset_id is not None:
            filters.append("kn2.dataset_id = :ds")
            params_base["ds"] = dataset_id
        if document_id is not None:
            filters.append("kn2.document_id = :doc")
            params_base["doc"] = document_id
        if embedding_model is not None:
            filters.append("kn2.embedding_model = :em")
            params_base["em"] = embedding_model
        where_clause = " AND ".join(filters)

        sql = f"""
            WITH q AS (SELECT vec FROM knowledge_nodes WHERE id = :id)
            SELECT kn2.id as node_id,
                   1.0 - (kn2.vec <-> (SELECT vec FROM q)) as score
            FROM knowledge_nodes kn2
            WHERE {where_clause}
            ORDER BY kn2.vec <-> (SELECT vec FROM q)
            LIMIT :k
        """

        for node_id in node_ids:
            params = dict(params_base)
            params["id"] = node_id
            rows = db.execute(text(sql), params).mappings().all()
            for row in rows:
                score = float(row["score"])
                if score < min_score:
                    continue
                _add_edge(edges, node_id, int(row["node_id"]), round(score, 4), "similarity")
                if len(edges) >= max_edges:
                    break
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
