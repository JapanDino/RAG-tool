from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db.session import get_db
from ..models.models import Dataset

router = APIRouter(prefix="/datasets", tags=["status"])

@router.get("/{dataset_id}/status")
def dataset_status(dataset_id: int, db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    q = """
    with
      doc as (select count(*) c from documents where dataset_id=:ds),
      ch as (select count(*) c from chunks where document_id in (select id from documents where dataset_id=:ds)),
      em as (select count(*) c from embeddings e join chunks c on c.id=e.chunk_id join documents d on d.id=c.document_id where d.dataset_id=:ds),
      an as (select count(*) c from bloom_annotations a join chunks c on c.id=a.chunk_id join documents d on d.id=c.document_id where d.dataset_id=:ds),
      last_job as (
        select id, type::text as type, status::text as status, task_id, created_at, finished_at
        from jobs
        where payload ? 'dataset_id' and (payload->>'dataset_id')::int = :ds
        order by created_at desc limit 1
      )
    select
      (select c from doc) as documents,
      (select c from ch) as chunks,
      (select c from em) as embeddings,
      (select c from an) as annotations,
      row_to_json(last_job.*)::json as last_job
    from last_job
    union all
    select
      (select c from doc),
      (select c from ch),
      (select c from em),
      (select c from an),
      null::json
    where not exists (select 1 from last_job)
    limit 1;
    """
    row = db.execute(text(q), {"ds": dataset_id}).mappings().first()
    return row or {
        "documents": 0,
        "chunks": 0,
        "embeddings": 0,
        "annotations": 0,
        "last_job": None,
    }
