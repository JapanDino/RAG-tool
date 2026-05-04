import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import KnowledgeNode
from ..schemas.schemas import (
    KnowledgeNodeBulkIn,
    KnowledgeNodeListOut,
    KnowledgeNodeOut,
    KnowledgeNodeSearchHit,
    KnowledgeNodeUpdateIn,
)
from ..services.embedding_provider import current_embedding_model
from ..services.query_embed import embed_query
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..utils.vector import vector_literal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("", response_model=KnowledgeNodeListOut)
def create_nodes(payload: KnowledgeNodeBulkIn, db: Session = Depends(get_db)):
    embedding_model = current_embedding_model()
    items: list[KnowledgeNode] = []

    # Collect nodes that need prob_vector or vec computed.
    needs_classify: list[int] = []   # index into items
    needs_embed: list[int] = []      # index into items

    for node in payload.nodes:
        obj = KnowledgeNode(
            dataset_id=node.dataset_id,
            document_id=node.document_id,
            chunk_id=node.chunk_id,
            title=node.title,
            context_text=node.context_text,
            prob_vector=node.prob_vector or [],
            top_levels=node.top_levels or [],
            embedding_dim=node.embedding_dim if node.embedding_dim is not None else 1536,
            embedding_model=node.embedding_model or embedding_model,
            version=node.version if node.version is not None else 1,
            model_info=node.model_info or {},
        )
        db.add(obj)
        idx = len(items)
        items.append(obj)

        if node.prob_vector is None:
            needs_classify.append(idx)
        if node.vec is None:
            needs_embed.append(idx)

    # Compute Bloom prob_vector for nodes that don't have it.
    for idx in needs_classify:
        node_obj = items[idx]
        text_for_classify = node_obj.context_text or node_obj.title
        try:
            cls = classify_bloom_multilabel(text_for_classify)
            node_obj.prob_vector = cls["prob_vector"]
            node_obj.top_levels = cls.get("top_levels", [])
        except Exception as exc:
            logger.warning("classify_bloom_multilabel failed for node %r: %s", node_obj.title, exc)

    # Compute semantic embeddings for nodes that don't have vec.
    if needs_embed:
        texts_to_embed = [
            f"{items[i].title}. {items[i].context_text}".strip()
            for i in needs_embed
        ]
        try:
            vecs = embed_texts(texts_to_embed, dim=1536)
            for i, vec in zip(needs_embed, vecs):
                items[i].vec = vec
                items[i].embedding_model = embedding_model
        except Exception as exc:
            logger.warning("embed_texts failed during create_nodes: %s", exc)

    db.commit()
    for obj in items:
        db.refresh(obj)
    return {"total": len(items), "items": items}


@router.get("", response_model=KnowledgeNodeListOut)
def list_nodes(
    dataset_id: int | None = None,
    document_id: int | None = None,
    document_ids: list[int] | None = Query(None),
    chunk_id: int | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeNode)
    if dataset_id is not None:
        query = query.filter(KnowledgeNode.dataset_id == dataset_id)
    if document_id is not None:
        query = query.filter(KnowledgeNode.document_id == document_id)
    if document_ids:
        query = query.filter(KnowledgeNode.document_id.in_(document_ids))
    if chunk_id is not None:
        query = query.filter(KnowledgeNode.chunk_id == chunk_id)

    total = query.count()
    items = query.order_by(KnowledgeNode.id.asc()).offset(offset).limit(limit).all()
    return {"total": total, "items": items}


@router.get("/search", response_model=list[KnowledgeNodeSearchHit])
def search_nodes(
    q: str = Query(..., min_length=1),
    dataset_id: int | None = None,
    embedding_model: str | None = None,
    top_k: int = 5,
    dim: int = 1536,
    db: Session = Depends(get_db),
):
    if dim != 1536:
        raise HTTPException(400, "dim must be 1536 for current storage")
    effective_model = embedding_model or current_embedding_model()
    try:
        qvec = embed_query(q, dim=dim, embedding_model=effective_model)
    except Exception as exc:
        raise HTTPException(400, f"cannot build query embedding for model '{effective_model}': {exc}")
    lit = vector_literal(qvec)
    filters = ["kn.vec IS NOT NULL", "kn.embedding_model = :em"]
    params = {"qvec": lit, "k": top_k, "em": effective_model}
    if dataset_id is not None:
        filters.append("kn.dataset_id = :ds")
        params["ds"] = dataset_id
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"""
        WITH q AS (SELECT CAST(:qvec AS vector) AS v)
        SELECT kn.id as node_id,
               kn.title,
               kn.context_text,
               kn.dataset_id,
               kn.document_id,
               kn.chunk_id,
               1.0 - (kn.vec <=> (SELECT v FROM q)) as score
        FROM knowledge_nodes kn
        {where_clause}
        ORDER BY kn.vec <=> (SELECT v FROM q)
        LIMIT :k
    """
    rows = db.execute(text(sql), params).mappings().all()
    return rows


@router.get("/{node_id}", response_model=KnowledgeNodeOut)
def get_node(node_id: int, db: Session = Depends(get_db)):
    node = db.get(KnowledgeNode, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    return node


@router.put("/{node_id}", response_model=KnowledgeNodeOut)
def update_node(node_id: int, payload: KnowledgeNodeUpdateIn, db: Session = Depends(get_db)):
    node = db.get(KnowledgeNode, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    if payload.title is not None:
        node.title = payload.title
    if payload.context_text is not None:
        node.context_text = payload.context_text
    if payload.prob_vector is not None:
        node.prob_vector = payload.prob_vector
    if payload.top_levels is not None:
        node.top_levels = payload.top_levels
    if payload.embedding_dim is not None:
        node.embedding_dim = payload.embedding_dim
    if payload.embedding_model is not None:
        node.embedding_model = payload.embedding_model
    if payload.version is not None:
        node.version = payload.version
    if payload.model_info is not None:
        node.model_info = payload.model_info
    db.commit()
    db.refresh(node)
    return node


@router.delete("/{node_id}")
def delete_node(node_id: int, db: Session = Depends(get_db)):
    node = db.get(KnowledgeNode, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    db.delete(node)
    db.commit()
    return {"ok": True}
