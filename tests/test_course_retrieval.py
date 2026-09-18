import time

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.base import Base
from backend.app.models.models import Chunk, Course, CourseModule, Dataset, Document
from backend.app.services.course_retrieval import (
    RetrievalDeadlineExceeded,
    hybrid_text_scores,
    retrieve_course_context,
)


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, future=True)()


def _course_with_document(db, suffix: str, text: str):
    dataset = Dataset(name=f"retrieval-{suffix}")
    db.add(dataset)
    db.flush()
    course = Course(
        dataset_id=dataset.id, title=f"Course {suffix}", source_type="canvas"
    )
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, title="Алгоритмы", position=1)
    db.add(module)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        course_module_id=module.id,
        title=f"Материал {suffix}",
        source=f"https://canvas.example.edu/courses/{suffix}/pages/sorting",
        status="ready",
        source_metadata={"document_type": "lecture_material"},
    )
    db.add(document)
    db.flush()
    chunk = Chunk(document_id=document.id, idx=0, text=text, meta={})
    db.add(chunk)
    db.commit()
    return course, module, document, chunk


def test_retrieval_rejects_an_expired_deadline_before_work_starts():
    engine, db = _db()
    course, _, _, _ = _course_with_document(db, "deadline", "bounded retrieval")

    with pytest.raises(RetrievalDeadlineExceeded):
        retrieve_course_context(
            db,
            course,
            "bounded retrieval",
            deadline_monotonic=time.monotonic() - 1,
        )

    db.close()
    engine.dispose()


def test_retrieval_caps_remote_embedding_to_remaining_deadline(monkeypatch):
    captured = []

    def bounded_embeddings(texts, *, timeout_seconds=None, **kwargs):
        captured.append(timeout_seconds)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "backend.app.services.course_retrieval.embed_texts",
        bounded_embeddings,
    )
    combined, lexical, semantic, _ = hybrid_text_scores(
        "sorting algorithms",
        ["sorting algorithms"],
        deadline_monotonic=time.monotonic() + 1.0,
    )

    assert combined and lexical and semantic
    assert captured and 0 < captured[0] <= 1.0


def test_retrieval_is_scoped_to_one_course_and_keeps_canvas_source(monkeypatch):
    engine, db = _db()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    first, module, document, chunk = _course_with_document(
        db,
        "one",
        "Quicksort и mergesort сравнивают по временной сложности и использованию памяти.",
    )
    _course_with_document(db, "two", "Quicksort встречается и в другом закрытом курсе.")

    hits, method = retrieve_course_context(
        db,
        first,
        "сравнить quicksort mergesort по временной сложности",
        module_id=module.id,
        document_types={"lecture_material"},
        top_k=5,
        min_score=0.01,
    )

    assert hits
    assert {item.document_id for item in hits} == {document.id}
    assert hits[0].chunk_id == chunk.id
    assert hits[0].source_url.endswith("/pages/sorting")
    assert hits[0].module_bonus == 1.0
    assert "hybrid_bm25" in method
    db.close()
    engine.dispose()


def test_module_scoped_retrieval_never_returns_another_module(monkeypatch):
    engine, db = _db()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    course, selected_module, _, _ = _course_with_document(
        db,
        "strict-module",
        "Материал выбранного раздела объясняет проверяемые цитаты.",
    )
    other_module = CourseModule(course_id=course.id, title="Другой раздел", position=2)
    db.add(other_module)
    db.flush()
    other_document = Document(
        dataset_id=course.dataset_id,
        course_module_id=other_module.id,
        title="Закрытый соседний контекст",
        source="https://canvas.example.edu/courses/strict-module/pages/other",
        status="ready",
        source_metadata={"document_type": "lecture_material"},
    )
    db.add(other_document)
    db.flush()
    db.add(
        Chunk(
            document_id=other_document.id,
            idx=0,
            text="Уникальный термин ксеноконтекст находится только в другом разделе.",
            meta={},
        )
    )
    db.commit()

    hits, _ = retrieve_course_context(
        db,
        course,
        "ксеноконтекст",
        module_id=selected_module.id,
        document_types={"lecture_material"},
        top_k=5,
        min_score=0.01,
    )

    assert all(hit.module_id == selected_module.id for hit in hits)
    assert all(hit.document_id != other_document.id for hit in hits)
    db.close()
    engine.dispose()


def test_retrieval_returns_empty_for_unrelated_query_with_threshold(monkeypatch):
    engine, db = _db()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    course, _, _, _ = _course_with_document(
        db, "empty", "Теория графов и обход в ширину."
    )
    hits, _ = retrieve_course_context(
        db,
        course,
        "квантовая хромодинамика",
        top_k=3,
        min_score=0.2,
    )
    assert hits == []
    db.close()
    engine.dispose()


def test_student_retrieval_fails_closed_for_hidden_processing_and_wrong_types(
    monkeypatch,
):
    engine, db = _db()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    dataset = Dataset(name="student-visible-boundary")
    db.add(dataset)
    db.flush()
    course = Course(
        dataset_id=dataset.id,
        title="Canvas boundary",
        source_type="canvas",
    )
    db.add(course)
    db.flush()

    documents = [
        Document(
            dataset_id=dataset.id,
            title="Published lecture",
            source="https://canvas.example.edu/pages/published",
            status="ready",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Unpublished lecture",
            source="https://canvas.example.edu/pages/unpublished",
            status="ready",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
                "canvas_published": False,
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Malformed unlock lecture",
            source="https://canvas.example.edu/pages/malformed-unlock",
            status="ready",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
                "unlock_at": "not-a-timestamp",
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Malformed lock lecture",
            source="https://canvas.example.edu/pages/malformed-lock",
            status="ready",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
                "lock_at": "tomorrow-ish",
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Future locked lecture",
            source="https://canvas.example.edu/pages/future",
            status="ready",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
                "unlock_at": "2099-01-01T00:00:00Z",
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Prerequisite locked lecture",
            source="https://canvas.example.edu/pages/prerequisite-locked",
            status="ready",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
                "module_state": "locked",
                "module_prerequisite_ids": [4],
                "module_require_sequential_progress": True,
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Processing lecture",
            source="https://canvas.example.edu/pages/processing",
            status="processing",
            source_metadata={
                "document_type": "lecture_material",
                "student_visible": True,
            },
        ),
        Document(
            dataset_id=dataset.id,
            title="Published quiz",
            source="https://canvas.example.edu/quizzes/secret",
            status="ready",
            source_metadata={
                "document_type": "quiz",
                "student_visible": True,
            },
        ),
    ]
    db.add_all(documents)
    db.flush()
    for document in documents:
        db.add(
            Chunk(
                document_id=document.id,
                idx=0,
                text=f"shared boundary phrase from {document.title}",
                meta={},
            )
        )
    db.commit()

    hits, _ = retrieve_course_context(
        db,
        course,
        "shared boundary phrase",
        document_types={"lecture_material"},
        student_visible_only=True,
        top_k=8,
        min_score=0.0,
    )
    assert [hit.document_id for hit in hits] == [documents[0].id]

    no_matching_type, _ = retrieve_course_context(
        db,
        course,
        "shared boundary phrase",
        document_types={"reference"},
        top_k=8,
        min_score=0.0,
    )
    assert no_matching_type == []
    db.close()
    engine.dispose()


def test_retrieval_ranks_relevant_chunks_before_candidate_cap(monkeypatch):
    engine, db = _db()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    dataset = Dataset(name="candidate-ranking")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Large course", source_type="manual")
    db.add(course)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        title="Large reader",
        source="manual://large-reader",
        status="ready",
        source_metadata={"document_type": "lecture_material"},
    )
    db.add(document)
    db.flush()
    for index in range(500):
        db.add(
            Chunk(
                document_id=document.id,
                idx=index,
                text=f"generic filler passage {index}",
                meta={},
            )
        )
    target = Chunk(
        document_id=document.id,
        idx=500,
        text="The unique zephyrneedle concept means evidence after the candidate cap.",
        meta={},
    )
    db.add(target)
    db.commit()

    hits, _ = retrieve_course_context(
        db,
        course,
        "What does zephyrneedle mean?",
        top_k=3,
        max_candidates=500,
        min_score=0.01,
    )
    assert hits
    assert hits[0].chunk_id == target.id
    db.close()
    engine.dispose()
