from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import KnowledgeNode
from ..schemas.schemas import (
    KnowledgeNodeBulkIn,
    KnowledgeNodeListOut,
    KnowledgeNodeOut,
    KnowledgeNodeUpdateIn,
)

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("", response_model=KnowledgeNodeListOut)
def create_nodes(payload: KnowledgeNodeBulkIn, db: Session = Depends(get_db)):
    items: list[KnowledgeNode] = []
    for node in payload.nodes:
        obj = KnowledgeNode(
            dataset_id=node.dataset_id,
            document_id=node.document_id,
            chunk_id=node.chunk_id,
            title=node.title,
            context_text=node.context_text,
            prob_vector=node.prob_vector,
            top_levels=node.top_levels,
            embedding_dim=(
                node.embedding_dim if node.embedding_dim is not None else 1536
            ),
            embedding_model=node.embedding_model or "text-embedding-3-small",
            version=node.version if node.version is not None else 1,
            model_info=node.model_info or {},
        )
        db.add(obj)
        items.append(obj)
    db.commit()
    for obj in items:
        db.refresh(obj)
    return {"total": len(items), "items": items}


@router.get("", response_model=KnowledgeNodeListOut)
def list_nodes(
    dataset_id: int | None = None,
    document_id: int | None = None,
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
    if chunk_id is not None:
        query = query.filter(KnowledgeNode.chunk_id == chunk_id)

    total = query.count()
    items = query.order_by(KnowledgeNode.id.asc()).offset(offset).limit(limit).all()
    return {"total": total, "items": items}


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
