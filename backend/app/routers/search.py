from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db.session import get_db
from ..services.query_embed import embed_query
from ..utils.vector import vector_literal

router = APIRouter(prefix="/search", tags=["search"])

@router.get("")
def search(q: str = Query(..., min_length=1), dataset_id: int | None = None, top_k: int = 5, dim: int = 1536, db: Session = Depends(get_db)):
    qvec = embed_query(q, dim=dim)
    lit = vector_literal(qvec)
    sql = """
        WITH q AS (SELECT :qvec::vector AS v)
        SELECT c.id as chunk_id, c.text,
               d.id as document_id, d.title as document_title,
               1.0 - (e.vec <-> (SELECT v FROM q)) as score
        FROM embeddings e
        JOIN chunks c ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        {ds_filter}
        ORDER BY e.vec <-> (SELECT v FROM q)
        LIMIT :k
    """
    ds_filter = "WHERE d.dataset_id = :ds" if dataset_id is not None else ""
    rows = db.execute(text(sql.format(ds_filter=ds_filter)), {
        "qvec": lit,
        "k": top_k,
        **({"ds": dataset_id} if dataset_id is not None else {})
    }).mappings().all()
    return rows
