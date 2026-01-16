from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models.models import BloomAnnotation, BloomLevel, Chunk, Dataset, Document
from backend.app.utils.quality import (
    calculate_consistency_metrics,
    calculate_coverage_metrics,
    calculate_level_distribution,
    calculate_score_distribution,
)


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def test_score_and_level_distribution():
    annotations = [
        BloomAnnotation(level=BloomLevel.apply, label="a", rationale="r", score=0.2),
        BloomAnnotation(level=BloomLevel.apply, label="b", rationale="r", score=0.6),
        BloomAnnotation(level=BloomLevel.remember, label="c", rationale="r", score=0.8),
    ]
    scores = calculate_score_distribution(annotations)
    levels = calculate_level_distribution(annotations)

    assert scores["count"] == 3
    assert scores["min"] == 0.2
    assert scores["max"] == 0.8
    assert levels["apply"] == 2
    assert levels["remember"] == 1


def test_consistency_and_coverage_metrics():
    db = _make_session()
    dataset = Dataset(name="dataset-1")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    document = Document(dataset_id=dataset.id, title="doc", source="test")
    db.add(document)
    db.commit()
    db.refresh(document)

    chunk1 = Chunk(document_id=document.id, idx=0, text="A", meta={})
    chunk2 = Chunk(document_id=document.id, idx=1, text="B", meta={})
    db.add_all([chunk1, chunk2])
    db.commit()
    db.refresh(chunk1)
    db.refresh(chunk2)

    annotations = [
        BloomAnnotation(
            chunk_id=chunk1.id,
            level=BloomLevel.apply,
            label="a",
            rationale="r",
            score=0.1,
        ),
        BloomAnnotation(
            chunk_id=chunk1.id,
            level=BloomLevel.remember,
            label="b",
            rationale="r",
            score=0.9,
        ),
    ]
    db.add_all(annotations)
    db.commit()

    consistency = calculate_consistency_metrics(chunk1.id, db)
    coverage = calculate_coverage_metrics(dataset.id, db)

    assert consistency["annotations"] == 2
    assert consistency["levels_present"] == 2
    assert coverage["chunks_total"] == 2
    assert coverage["chunks_annotated"] == 1

