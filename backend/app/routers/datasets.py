import logging
import uuid
import os

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import Dataset, Document, Job, JobType, JobStatus
from ..tasks.queue import enqueue_or_mark
from ..schemas.schemas import DatasetIn, DatasetOut
from ..services.text_extract import extract_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))  # 20 MB default


@router.get("", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    return db.query(Dataset).order_by(Dataset.id).all()


@router.post("", response_model=DatasetOut)
def create_dataset(data: DatasetIn, db: Session = Depends(get_db)):
    existing = db.query(Dataset).filter(Dataset.name == data.name).first()
    if existing:
        return existing
    ds = Dataset(name=data.name)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds

@router.post("/extract-text")
def extract_text_from_file(file: UploadFile = File(...)):
    data = file.file.read()
    result = extract_text(file.filename or "", file.content_type or "", data)
    return {"text": result}


@router.post("/{dataset_id}/documents")
def upload_document(dataset_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    ext = os.path.splitext(filename)[1] if "." in filename else ""
    file_uuid = str(uuid.uuid4())

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = f"{UPLOAD_DIR}/{file_uuid}{ext}"
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)")
    with open(file_path, "wb") as f:
        f.write(data)

    doc = Document(
        dataset_id=dataset_id,
        title=filename,
        source=f"upload://{file_uuid}",
        mime=content_type,
        status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    job = Job(
        type=JobType.parse,
        status=JobStatus.queued,
        payload={
            "document_id": doc.id,
            "file_path": file_path,
            "filename": filename,
            "content_type": content_type,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_or_mark(db, job)

    return {"document_id": doc.id, "job_id": job.id}

@router.post("/{dataset_id}/index")
def start_index(dataset_id: int, db: Session = Depends(get_db)):
    job = Job(type=JobType.index, status=JobStatus.queued, payload={"dataset_id": dataset_id})
    db.add(job); db.commit(); db.refresh(job)
    enqueue_or_mark(db, job)
    return {"job_id": job.id}

@router.post("/{dataset_id}/annotate")
def start_annotate(dataset_id: int, level: str = Query(..., pattern="^(remember|understand|apply|analyze|evaluate|create)$"), db: Session = Depends(get_db)):
    job = Job(type=JobType.annotate, status=JobStatus.queued, payload={"dataset_id": dataset_id, "level": level})
    db.add(job); db.commit(); db.refresh(job)
    enqueue_or_mark(db, job)
    return {"job_id": job.id}


@router.get("/{dataset_id}/stats")
def dataset_stats(dataset_id: int, db: Session = Depends(get_db)):
    """Aggregated stats for the dashboard: Bloom dist, confidence, documents, jobs, labels."""
    from collections import defaultdict
    from ..models.models import KnowledgeNode, NodeLabel

    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    # ── Nodes (no vectors needed) ─────────────────────────────
    node_rows = db.execute(
        text("""
            SELECT id, document_id, top_levels, prob_vector, embedding_model, title
            FROM knowledge_nodes WHERE dataset_id = :ds
        """),
        {"ds": dataset_id},
    ).mappings().all()

    # ── Documents with node counts ────────────────────────────
    doc_rows = db.execute(
        text("""
            SELECT d.id, d.title, d.source, d.status,
                   COUNT(kn.id) AS node_count
            FROM documents d
            LEFT JOIN knowledge_nodes kn ON kn.document_id = d.id
            WHERE d.dataset_id = :ds
            GROUP BY d.id, d.title, d.source, d.status
            ORDER BY node_count DESC
            LIMIT 100
        """),
        {"ds": dataset_id},
    ).mappings().all()

    # ── Recent jobs ───────────────────────────────────────────
    recent_jobs = (
        db.query(Job)
        .filter(Job.payload["dataset_id"].as_integer() == dataset_id)
        .order_by(Job.id.desc())
        .limit(15)
        .all()
    )

    # ── Label count ───────────────────────────────────────────
    labeled_count = (
        db.query(NodeLabel)
        .join(KnowledgeNode, NodeLabel.node_id == KnowledgeNode.id)
        .filter(KnowledgeNode.dataset_id == dataset_id)
        .count()
    )

    # ── Aggregations ──────────────────────────────────────────
    bloom_dist: dict[str, int] = defaultdict(int)
    conf_dist = {"high": 0, "medium": 0, "low": 0}
    model_dist: dict[str, int] = defaultdict(int)

    for row in node_rows:
        for lvl in (row["top_levels"] or []):
            bloom_dist[str(lvl)] += 1
        model_dist[str(row["embedding_model"] or "unknown")] += 1
        probs = list(row["prob_vector"] or [])
        if probs:
            sp = sorted(probs, reverse=True)
            p0 = sp[0]
            gap = p0 - (sp[1] if len(sp) > 1 else 0.0)
            if p0 >= 0.45 and gap >= 0.15:
                conf_dist["high"] += 1
            elif p0 >= 0.30 and gap >= 0.07:
                conf_dist["medium"] += 1
            else:
                conf_dist["low"] += 1

    active_statuses = {"queued", "running"}
    active_jobs = sum(1 for j in recent_jobs if str(j.status) in active_statuses)

    return {
        "dataset_id": dataset_id,
        "dataset_name": ds.name,
        "node_count": len(node_rows),
        "document_count": len(doc_rows),
        "labeled_count": labeled_count,
        "bloom_distribution": dict(bloom_dist),
        "confidence_distribution": conf_dist,
        "model_distribution": dict(model_dist),
        "documents": [
            {
                "id": int(r["id"]),
                "title": str(r["title"] or "Без названия"),
                "source": str(r["source"] or ""),
                "status": str(r["status"] or "unknown"),
                "node_count": int(r["node_count"] or 0),
            }
            for r in doc_rows
        ],
        "recent_jobs": [
            {
                "id": j.id,
                "type": str(j.type).split(".")[-1],
                "status": str(j.status).split(".")[-1],
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                "error": j.error,
            }
            for j in recent_jobs
        ],
        "active_jobs": active_jobs,
    }


@router.post("/{dataset_id}/reindex-nodes")
def reindex_nodes(dataset_id: int, db: Session = Depends(get_db)):
    """Re-embed all KnowledgeNodes in the dataset using the current EMBEDDING_PROVIDER.
    Enqueues an async Celery task and returns the job_id immediately.
    """
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")

    job = Job(type=JobType.graph, status=JobStatus.queued, payload={"dataset_id": dataset_id, "action": "reindex"})
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_or_mark(db, job)
    return {"job_id": job.id}
