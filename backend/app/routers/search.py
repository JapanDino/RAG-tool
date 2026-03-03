from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db.session import get_db
from ..services.query_embed import embed_query
from ..services.embedding_provider import current_embedding_model
from ..utils.vector import vector_literal

router = APIRouter(prefix="/search", tags=["search"])

@router.get("")
def search(
    q: str = Query(..., min_length=1),
    dataset_id: int | None = None,
    embedding_model: str | None = None,
    top_k: int = 5,
    dim: int = 1536,
    db: Session = Depends(get_db),
):
    if dim != 1536:
        raise HTTPException(400, "dim must be 1536 for current storage")
    qvec = embed_query(q, dim=dim)
    lit = vector_literal(qvec)
    em = embedding_model or current_embedding_model()
    sql = """
        WITH q AS (SELECT CAST(:qvec AS vector) AS v)
        SELECT c.id as chunk_id, c.text,
               d.id as document_id, d.title as document_title,
               1.0 - (e.vec <-> (SELECT v FROM q)) as score
        FROM embeddings e
        JOIN chunks c ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        {where_clause}
        ORDER BY e.vec <-> (SELECT v FROM q)
        LIMIT :k
    """
    filters = ["e.vec IS NOT NULL", "e.model = :em"]
    params: dict[str, object] = {"qvec": lit, "k": top_k, "em": em}
    if dataset_id is not None:
        filters.append("d.dataset_id = :ds")
        params["ds"] = dataset_id
    where_clause = "WHERE " + " AND ".join(filters)
    rows = db.execute(text(sql.format(where_clause=where_clause)), {
        **params
    }).mappings().all()
    return rows
