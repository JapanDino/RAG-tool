from backend.app.services.chunking import chunk_text_with_offsets


def test_parse_task_is_sqlite_portable_and_cleans_temp_file(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.models.base import Base
    from backend.app.models.models import Dataset, Document, Job, JobStatus, JobType
    from backend.app.tasks import tasks

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(tasks, "SessionLocal", Session)

    db = Session()
    dataset = Dataset(name="parse-task")
    db.add(dataset)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        title="text.txt",
        source="upload://test",
        status="processing",
    )
    db.add(document)
    db.flush()
    job = Job(type=JobType.parse, status=JobStatus.queued, payload={})
    db.add(job)
    db.commit()
    document_id, job_id = document.id, job.id
    db.close()

    path = tmp_path / "upload.txt"
    path.write_text(
        "Первое содержательное предложение. Второе содержательное предложение.",
        encoding="utf-8",
    )
    result = tasks.parse_document(
        document_id, str(path), "text.txt", "text/plain", job_id
    )
    assert result["ok"] is True
    assert not path.exists()

    db = Session()
    assert db.get(Document, document_id).status == "ready"
    assert db.get(Job, job_id).status == JobStatus.done
    assert db.get(Job, job_id).finished_at is not None
    db.close()
    engine.dispose()


def test_sentence_aware_chunks_preserve_source_offsets():
    text = (
        "Первая цель курса состоит в понимании структуры алгоритма. "
        "Студент должен сравнить два алгоритма сортировки. "
        "Затем он объясняет различия и оценивает сложность каждого решения."
    )
    chunks = chunk_text_with_offsets(text, max_chars=100, min_chars=40)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert text[chunk["start"] : chunk["end"]].strip() == chunk["text"]
        assert chunk["sentence_start"] <= chunk["sentence_end"]
