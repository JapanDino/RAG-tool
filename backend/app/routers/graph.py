from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import KnowledgeNode, KnowledgeEdge, Job, JobType, JobStatus
from ..schemas.schemas import (
    GraphOut,
    GraphNodeOut,
    GraphEdgeOut,
    GraphRebuildIn,
    GraphRebuildOut,
    GraphClusterOut,
    GraphClustersOut,
)
from ..utils.bloom import LEVEL_ORDER
from ..tasks.queue import enqueue_or_mark

router = APIRouter(prefix="/graph", tags=["graph"])


def _node_meta(node: KnowledgeNode) -> tuple[int | None, str | None]:
    model_info = node.model_info or {}
    if not isinstance(model_info, dict):
        return None, None
    frequency = model_info.get("frequency")
    rationale = model_info.get("rationale")
    return (int(frequency) if isinstance(frequency, (int, float)) else None, str(rationale) if rationale else None)


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
                frequency=_node_meta(n)[0],
                rationale=_node_meta(n)[1],
            )
            for n in nodes
        ]
        return GraphOut(nodes=node_items, edges=persisted_edges)

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
                   1.0 - (kn2.vec <=> (SELECT vec FROM q)) as score
            FROM knowledge_nodes kn2
            WHERE {where_clause}
            ORDER BY kn2.vec <=> (SELECT vec FROM q)
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
            frequency=_node_meta(n)[0],
            rationale=_node_meta(n)[1],
        )
        for n in nodes
    ]
    return GraphOut(nodes=node_items, edges=edge_items)


# ---------------------------------------------------------------------------
# ZPD — Zone of Proximal Development
# ---------------------------------------------------------------------------

@router.get("/zpd")
def get_zpd(
    node_id: int,
    top_k: int = Query(5, ge=1, le=50),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """Return top-K nodes at the next Bloom level closest to *node_id*.

    Given a node whose ``top_levels`` contains at least one Bloom level,
    finds the highest level present, looks up the next level in the taxonomy
    (remember → understand → apply → … → create), then returns the ``top_k``
    nodes at that next level ranked by pgvector cosine similarity.

    If the node is already at *create* (the highest level) or has no vector,
    the response is empty.
    """
    node = db.get(KnowledgeNode, node_id)
    if node is None:
        from fastapi import HTTPException
        raise HTTPException(404, "node not found")

    # Determine the node's current Bloom level (highest in top_levels).
    top_levels: list[str] = list(node.top_levels or [])
    current_idx: int | None = None
    for lvl in reversed(LEVEL_ORDER):       # highest first
        if lvl in top_levels:
            current_idx = LEVEL_ORDER.index(lvl)
            break

    if current_idx is None or current_idx >= len(LEVEL_ORDER) - 1 or node.vec is None:
        return {
            "node_id": node_id,
            "current_level": LEVEL_ORDER[current_idx] if current_idx is not None else None,
            "next_level": None,
            "suggestions": [],
        }

    next_level = LEVEL_ORDER[current_idx + 1]

    # pgvector cosine similarity query restricted to next_level nodes.
    sql = text("""
        SELECT kn.id,
               kn.title,
               kn.context_text,
               kn.prob_vector,
               kn.top_levels,
               kn.model_info,
               1.0 - (kn.vec <=> (SELECT vec FROM knowledge_nodes WHERE id = :id)) AS score
        FROM knowledge_nodes kn
        WHERE kn.id != :id
          AND kn.vec IS NOT NULL
          AND kn.top_levels @> :next_level_json::jsonb
        ORDER BY kn.vec <=> (SELECT vec FROM knowledge_nodes WHERE id = :id)
        LIMIT :k
    """)

    rows = db.execute(
        sql,
        {
            "id": node_id,
            "next_level_json": f'["{next_level}"]',
            "k": top_k,
        }
    ).mappings().all()

    suggestions = []
    for r in rows:
        score = float(r["score"])
        if score < min_score:
            continue
        mi = r.get("model_info") or {}
        freq = mi.get("frequency") if isinstance(mi, dict) else None
        rationale = mi.get("rationale") if isinstance(mi, dict) else None
        suggestions.append({
            "id": int(r["id"]),
            "title": str(r["title"]),
            "context_text": str(r["context_text"]),
            "prob_vector": list(r.get("prob_vector") or []),
            "top_levels": list(r.get("top_levels") or []),
            "similarity": round(score, 4),
            "frequency": int(freq) if freq is not None else None,
            "rationale": str(rationale) if rationale else None,
        })

    return {
        "node_id": node_id,
        "current_level": LEVEL_ORDER[current_idx],
        "next_level": next_level,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Clustering — collapse similar nodes into groups for large-graph view (>200)
# ---------------------------------------------------------------------------

class _DSU:
    """Union-Find / Disjoint Set Union for greedy clustering."""

    def __init__(self, ids: list[int]):
        self.parent: dict[int, int] = {i: i for i in ids}
        self.size: dict[int, int] = {i: 1 for i in ids}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]


@router.get("/clusters", response_model=GraphClustersOut)
def get_clusters(
    dataset_id: int | None = None,
    document_id: int | None = None,
    embedding_model: str | None = None,
    threshold: float = Query(0.55, ge=0.0, le=1.0, description="Min cosine similarity to merge nodes"),
    top_k: int = Query(8, ge=1, le=50, description="kNN per node when building edges on the fly"),
    limit_nodes: int = Query(2000, ge=1, le=20000),
    min_cluster_size: int = Query(1, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Collapse nodes into clusters of semantically close items.

    Designed for the >200-node regime where rendering every node individually
    degrades graph performance.  Uses persisted similarity edges when available
    (faster, deterministic) and falls back to live pgvector kNN otherwise.

    Algorithm: build a similarity graph with edge weight >= ``threshold``, then
    run Union-Find to obtain connected components.  Each component becomes a
    cluster.  For every cluster we return:

    * ``representative_title`` — the highest-frequency node title in the
      component (or first by id if frequencies are equal);
    * ``dominant_level`` — the Bloom level appearing most often across
      ``top_levels`` of cluster members;
    * ``avg_prob_vector`` — element-wise mean of probability vectors,
      re-normalised to sum to 1.
    """
    # --- 1. fetch candidate nodes ----------------------------------------
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
        SELECT kn.id FROM knowledge_nodes kn
        WHERE {where_clause}
        ORDER BY kn.id ASC
        LIMIT :limit
    """
    node_ids = [row[0] for row in db.execute(text(ids_sql), params).all()]
    if not node_ids:
        return GraphClustersOut(
            dataset_id=dataset_id,
            total_nodes=0,
            total_clusters=0,
            threshold=threshold,
            clusters=[],
        )

    nodes = (
        db.query(KnowledgeNode)
        .filter(KnowledgeNode.id.in_(node_ids))
        .all()
    )
    node_by_id = {n.id: n for n in nodes}

    # --- 2. collect similarity edges -------------------------------------
    edges: list[tuple[int, int, float]] = []

    # 2a. persisted edges (preferred)
    method_filters = [KnowledgeEdge.method.like("similarity|%")]
    persisted_rows = (
        db.query(KnowledgeEdge.from_node_id, KnowledgeEdge.to_node_id, KnowledgeEdge.weight)
        .filter(
            KnowledgeEdge.from_node_id.in_(node_ids),
            KnowledgeEdge.to_node_id.in_(node_ids),
            or_(*method_filters),
            KnowledgeEdge.weight >= threshold,
        )
        .all()
    )
    for a, b, w in persisted_rows:
        edges.append((int(a), int(b), float(w)))

    # 2b. fall back to live pgvector kNN when no persisted edges
    if not edges:
        in_clause_params: dict[str, object] = {"k": top_k, "threshold": threshold}
        ds_filter = ""
        if dataset_id is not None:
            ds_filter = "AND kn2.dataset_id = :ds"
            in_clause_params["ds"] = dataset_id
        sql = text(f"""
            SELECT kn2.id AS node_id,
                   1.0 - (kn2.vec <=> (SELECT vec FROM knowledge_nodes WHERE id = :id)) AS score
            FROM knowledge_nodes kn2
            WHERE kn2.id != :id
              AND kn2.vec IS NOT NULL
              {ds_filter}
            ORDER BY kn2.vec <=> (SELECT vec FROM knowledge_nodes WHERE id = :id)
            LIMIT :k
        """)
        for node_id in node_ids:
            p = dict(in_clause_params)
            p["id"] = node_id
            rows = db.execute(sql, p).mappings().all()
            for row in rows:
                score = float(row["score"])
                if score < threshold:
                    continue
                edges.append((node_id, int(row["node_id"]), score))

    # --- 3. Union-Find ----------------------------------------------------
    dsu = _DSU(node_ids)
    for a, b, _w in edges:
        if a in node_by_id and b in node_by_id:
            dsu.union(a, b)

    # --- 4. group nodes by root ------------------------------------------
    groups: dict[int, list[int]] = defaultdict(list)
    for nid in node_ids:
        groups[dsu.find(nid)].append(nid)

    # --- 5. summarise each cluster ---------------------------------------
    out: list[GraphClusterOut] = []
    for cid, (root, member_ids) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        if len(member_ids) < min_cluster_size:
            continue
        members = [node_by_id[m] for m in member_ids if m in node_by_id]
        if not members:
            continue

        # representative — highest frequency, ties → smallest id
        def _freq(n: KnowledgeNode) -> int:
            mi = n.model_info or {}
            f = mi.get("frequency") if isinstance(mi, dict) else None
            try:
                return int(f) if f is not None else 1
            except (TypeError, ValueError):
                return 1
        rep = max(members, key=lambda n: (_freq(n), -n.id))

        # dominant Bloom level across top_levels
        level_counts: dict[str, int] = defaultdict(int)
        for n in members:
            for lvl in (n.top_levels or []):
                level_counts[str(lvl)] += 1
        dominant_level = max(level_counts.items(), key=lambda kv: kv[1])[0] if level_counts else None

        # average prob vector (mean, then renormalise to sum=1)
        avg = [0.0] * 6
        denom = 0
        for n in members:
            pv = list(n.prob_vector or [])
            if len(pv) == 6:
                for i, p in enumerate(pv):
                    avg[i] += float(p)
                denom += 1
        if denom > 0:
            avg = [x / denom for x in avg]
            s = sum(avg)
            if s > 0:
                avg = [round(x / s, 4) for x in avg]
        else:
            avg = [round(1 / 6, 4)] * 6

        sample = [n.title for n in sorted(members, key=lambda n: (-_freq(n), n.id))[:5]]
        out.append(GraphClusterOut(
            cluster_id=cid,
            size=len(members),
            member_ids=[n.id for n in members],
            representative_title=rep.title,
            dominant_level=dominant_level if dominant_level in {"remember","understand","apply","analyze","evaluate","create"} else None,
            avg_prob_vector=avg,
            sample_titles=sample,
        ))

    return GraphClustersOut(
        dataset_id=dataset_id,
        total_nodes=len(node_ids),
        total_clusters=len(out),
        threshold=threshold,
        clusters=out,
    )
