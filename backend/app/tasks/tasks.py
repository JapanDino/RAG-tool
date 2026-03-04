import logging
import os

from .celery_app import celery_app
from ..db.session import SessionLocal
from ..models.models import Chunk, Document
from ..services.embedding import embed_texts
from ..services.text_extract import extract_text as _extract_text
from ..services.embedding_provider import current_embedding_model
from ..services.validation import validate_annotation
from ..utils.bloom import annotate_bloom
from ..utils.rubrics import get_active_rubric
from ..services.llm import llm_annotate, ENABLE_LLM
from sqlalchemy import text
from datetime import datetime
from ..utils.vector import vector_literal

logger = logging.getLogger(__name__)

@celery_app.task
def index_dataset(dataset_id: int, job_id: int | None = None, dim: int = 1536):
    db = SessionLocal()
    try:
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='running' WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()
        chunks = db.query(Chunk).join(Chunk.document).filter(Chunk.document.has(dataset_id=dataset_id)).all()
        if not chunks:
            if job_id is not None:
                db.execute(
                    text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"),
                    {"id": job_id},
                )
                db.commit()
            return {"ok": True, "count": 0}
        vecs = embed_texts([c.text for c in chunks], dim=dim)
        model_name = current_embedding_model()
        for chunk, vec in zip(chunks, vecs):
            db.execute(
                text(
                    """
                    INSERT INTO embeddings (chunk_id, dim, model, vec)
                    VALUES (:cid, :dim, :model, CAST(:v AS vector))
                    ON CONFLICT (chunk_id)
                    DO UPDATE SET dim = EXCLUDED.dim,
                                  model = EXCLUDED.model,
                                  vec = EXCLUDED.vec
                    """
                ),
                dict(cid=chunk.id, dim=dim, model=model_name, v=vector_literal(vec)),
            )
        db.commit()
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()
        return {"ok": True, "count": len(chunks)}
    except Exception as e:
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                {"err": str(e), "id": job_id},
            )
            db.commit()
        raise
    finally:
        db.close()

@celery_app.task
def annotate_dataset(dataset_id: int, level: str, job_id: int | None = None):
    db = SessionLocal()
    try:
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='running' WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()
        chunks = db.query(Chunk).join(Chunk.document).filter(Chunk.document.has(dataset_id=dataset_id)).all()
        for c in chunks:
            rubric = get_active_rubric(level, db)
            rubric_text = rubric.description if rubric else None
            a = (
                llm_annotate(c.text, level, rubric_text)
                if ENABLE_LLM
                else annotate_bloom(c.text, level, rubric_text)
            )
            ok, err = validate_annotation(a)
            if not ok:
                logger.warning("Invalid annotation from LLM, falling back", extra={"error": err, "chunk_id": c.id})
                a = annotate_bloom(c.text, level)
                ok, err = validate_annotation(a)
                if not ok:
                    logger.error("Invalid heuristic annotation; skipping", extra={"error": err, "chunk_id": c.id})
                    continue
            db.execute(text("""
                INSERT INTO bloom_annotations (chunk_id, level, label, rationale, score)
                VALUES (:cid, :level, :label, :rationale, :score)
                ON CONFLICT (chunk_id, level)
                DO UPDATE SET label = EXCLUDED.label,
                              rationale = EXCLUDED.rationale,
                              score = EXCLUDED.score,
                              version = COALESCE(bloom_annotations.version, 1) + 1,
                              created_at = now()
            """), dict(cid=c.id, **a))
        db.commit()
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()
        return {"ok": True, "count": len(chunks)}
    except Exception as e:
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                {"err": str(e), "id": job_id},
            )
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task
def rebuild_graph_edges(
    dataset_id: int,
    job_id: int | None = None,
    embedding_model: str | None = None,
    top_k: int = 5,
    min_score: float = 0.2,
    max_edges: int = 200,
    include_cooccurrence: bool = True,
    limit_nodes: int = 500,
    co_window: int = 2,
):
    """
    Rebuilds and persists graph edges into `knowledge_edges`.
    Similarity edges are computed with pgvector (<->) over `knowledge_nodes.vec`.
    """
    from ..models.models import KnowledgeNode  # avoid circular import at module import time

    db = SessionLocal()
    try:
        if job_id is not None:
            db.execute(text("UPDATE jobs SET status='running' WHERE id=:id"), {"id": job_id})
            db.commit()

        em = embedding_model or current_embedding_model()
        sim_method = f"similarity|{em}"
        co_method = "co_occurrence_window"

        # Fetch candidate nodes.
        rows = db.execute(
            text(
                """
                SELECT id, document_id, model_info
                FROM knowledge_nodes
                WHERE dataset_id = :ds
                  AND vec IS NOT NULL
                  AND embedding_model = :em
                ORDER BY id ASC
                LIMIT :limit
                """
            ),
            {"ds": dataset_id, "em": em, "limit": limit_nodes},
        ).mappings().all()
        node_ids = [int(r["id"]) for r in rows]
        if not node_ids:
            db.execute(text("DELETE FROM knowledge_edges WHERE dataset_id=:ds"), {"ds": dataset_id})
            db.commit()
            if job_id is not None:
                db.execute(text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"), {"id": job_id})
                db.commit()
            return {"ok": True, "nodes": 0, "edges": 0}

        # Similarity edges.
        edge_map: dict[tuple[int, int, str], float] = {}

        def add_edge(a: int, b: int, weight: float, method: str):
            if a == b:
                return
            x, y = (a, b) if a < b else (b, a)
            key = (x, y, method)
            cur = edge_map.get(key)
            if cur is None or weight > cur:
                edge_map[key] = weight

        sql = """
            WITH q AS (SELECT vec FROM knowledge_nodes WHERE id = :id)
            SELECT kn2.id as node_id,
                   1.0 - (kn2.vec <-> (SELECT vec FROM q)) as score
            FROM knowledge_nodes kn2
            WHERE kn2.dataset_id = :ds
              AND kn2.embedding_model = :em
              AND kn2.vec IS NOT NULL
              AND kn2.id != :id
            ORDER BY kn2.vec <-> (SELECT vec FROM q)
            LIMIT :k
        """
        for nid in node_ids:
            if len(edge_map) >= max_edges:
                break
            r2 = db.execute(
                text(sql),
                {"id": nid, "ds": dataset_id, "em": em, "k": top_k},
            ).mappings().all()
            for row in r2:
                score = float(row["score"])
                if score < min_score:
                    continue
                add_edge(nid, int(row["node_id"]), round(score, 4), sim_method)
                if len(edge_map) >= max_edges:
                    break

        # Co-occurrence by document + sentence window.
        if include_cooccurrence and len(edge_map) < max_edges:
            by_doc: dict[int, list[tuple[int, int]]] = {}
            for r in rows:
                doc_id = r["document_id"]
                if doc_id is None:
                    continue
                mi = r["model_info"] or {}
                src = (mi.get("source") or {}) if isinstance(mi, dict) else {}
                sent_idx = src.get("sentence_idx")
                if sent_idx is None:
                    continue
                by_doc.setdefault(int(doc_id), []).append((int(sent_idx), int(r["id"])))

            for _doc_id, pairs in by_doc.items():
                pairs.sort(key=lambda x: x[0])
                for i in range(len(pairs)):
                    si, a = pairs[i]
                    # connect to next nodes within window
                    for j in range(i + 1, len(pairs)):
                        sj, b = pairs[j]
                        if (sj - si) > co_window:
                            break
                        add_edge(a, b, 0.5, co_method)
                        if len(edge_map) >= max_edges:
                            break
                    if len(edge_map) >= max_edges:
                        break
                if len(edge_map) >= max_edges:
                    break

        # Persist edges.
        db.execute(text("DELETE FROM knowledge_edges WHERE dataset_id=:ds"), {"ds": dataset_id})
        if edge_map:
            payload = [
                {
                    "ds": dataset_id,
                    "a": a,
                    "b": b,
                    "w": w,
                    "m": m,
                }
                for (a, b, m), w in edge_map.items()
            ]
            db.execute(
                text(
                    """
                    INSERT INTO knowledge_edges (dataset_id, from_node_id, to_node_id, weight, method)
                    VALUES (:ds, :a, :b, :w, :m)
                    ON CONFLICT (dataset_id, from_node_id, to_node_id, method)
                    DO UPDATE SET weight = GREATEST(knowledge_edges.weight, EXCLUDED.weight)
                    """
                ),
                payload,
            )
        db.commit()

        if job_id is not None:
            db.execute(text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"), {"id": job_id})
            db.commit()
        return {"ok": True, "nodes": len(node_ids), "edges": len(edge_map)}
    except Exception as e:
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                {"err": str(e), "id": job_id},
            )
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task
def parse_document(document_id: int, file_path: str, filename: str,
                   content_type: str, job_id: int | None = None):
    """Read a saved file, run text extraction (full OCR if needed), create Chunks,
    mark Document as ready, delete the temp file, and mark the job done."""
    db = SessionLocal()
    try:
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='running' WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()

        with open(file_path, "rb") as f:
            data = f.read()

        text_str = _extract_text(filename, content_type, data)
        parts = [text_str[i:i+800] for i in range(0, len(text_str), 800)]

        db.execute(
            text("DELETE FROM chunks WHERE document_id=:did"),
            {"did": document_id},
        )
        for i, p in enumerate(parts):
            db.add(Chunk(document_id=document_id, idx=i, text=p, meta={}))

        db.execute(
            text("UPDATE documents SET status='ready' WHERE id=:id"),
            {"id": document_id},
        )
        db.commit()

        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning("Could not delete temp file %s: %s", file_path, e)

        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='done', finished_at=now() WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()

        return {"ok": True, "document_id": document_id, "chunks": len(parts)}
    except Exception as e:
        db.execute(
            text("UPDATE documents SET status='failed' WHERE id=:id"),
            {"id": document_id},
        )
        if job_id is not None:
            db.execute(
                text("UPDATE jobs SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                {"err": str(e), "id": job_id},
            )
        db.commit()
        raise
    finally:
        db.close()
