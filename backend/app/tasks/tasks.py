from .celery_app import celery_app
from ..db.session import SessionLocal
from ..models.models import Chunk
from ..services.embedding import embed_texts
from ..utils.bloom import annotate_bloom
from ..services.llm import llm_annotate, ENABLE_LLM
from sqlalchemy import text
from datetime import datetime

@celery_app.task
def index_dataset(dataset_id: int, dim: int = 1536):
    db = SessionLocal()
    try:
        chunks = db.query(Chunk).join(Chunk.document).filter(Chunk.document.has(dataset_id=dataset_id)).all()
        if not chunks:
            return {"ok": True, "count": 0}
        vecs = embed_texts([c.text for c in chunks], dim=dim)
        for chunk, vec in zip(chunks, vecs):
            db.execute(text("INSERT INTO embeddings (chunk_id, dim, model) VALUES (:cid, :dim, :model) ON CONFLICT DO NOTHING"),
                       dict(cid=chunk.id, dim=dim, model="text-embedding-3-small"))
            db.execute(text("UPDATE embeddings SET vec = :v::vector WHERE chunk_id=:cid"),
                       dict(v=str(vec), cid=chunk.id))
        db.commit()
        return {"ok": True, "count": len(chunks)}
    finally:
        db.close()

@celery_app.task
def annotate_dataset(dataset_id: int, level: str):
    db = SessionLocal()
    try:
        chunks = db.query(Chunk).join(Chunk.document).filter(Chunk.document.has(dataset_id=dataset_id)).all()
        for c in chunks:
            a = llm_annotate(c.text, level) if ENABLE_LLM else annotate_bloom(c.text, level)
            db.execute(text("""
                INSERT INTO bloom_annotations (chunk_id, level, label, rationale, score)
                VALUES (:cid, :level, :label, :rationale, :score)
            """), dict(cid=c.id, **a))
        db.commit()
        return {"ok": True, "count": len(chunks)}
    finally:
        db.close()
