from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.models import Dataset, Document, Job, JobType, JobStatus
from ..tasks.queue import enqueue_or_mark
from ..schemas.schemas import DatasetIn, DatasetOut
from ..services.text_extract import extract_text
import uuid
import os

router = APIRouter(prefix="/datasets", tags=["datasets"])


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

    os.makedirs("/app/uploads", exist_ok=True)
    file_path = f"/app/uploads/{file_uuid}{ext}"
    data = file.file.read()
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
