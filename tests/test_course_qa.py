import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.models import (
    AssessmentItem,
    Chunk,
    Course,
    CourseModule,
    CourseQuestionAnswer,
    Dataset,
    Document,
)
from backend.app.services.course_qa import answer_course_question


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session, Session()


def _seed(db):
    dataset = Dataset(name="qa-course")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Algorithms", source_type="canvas")
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, title="Sorting", position=1)
    db.add(module)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        course_module_id=module.id,
        title="Sorting lecture",
        source="https://canvas.example.edu/courses/1/pages/sorting",
        status="ready",
        source_metadata={
            "document_type": "lecture_material",
            "student_visible": True,
        },
    )
    db.add(document)
    db.flush()
    db.add(
        Chunk(
            document_id=document.id,
            idx=0,
            text="Quicksort has average time complexity O(n log n), while its worst case is O(n squared).",
            meta={},
        )
    )
    db.commit()
    return course, module, document


def test_course_qa_validates_llm_citations_and_falls_back(monkeypatch):
    engine, _, db = _db()
    course, module, document = _seed(db)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("COURSE_QA_PROVIDER", "litellm")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")

    monkeypatch.setattr(
        "backend.app.services.course_qa.chat_completion_json",
        lambda *args, **kwargs: json.dumps(
            {
                "answer": "Средняя сложность quicksort — O(n log n).",
                "citation_ids": ["S1"],
                "confidence": 0.84,
                "insufficient_context": False,
            }
        ),
    )
    answer = answer_course_question(
        db, course, "Какова средняя сложность quicksort?", module_id=module.id
    )
    assert answer.generation_provider == "litellm"
    assert answer.citations[0].document_id == document.id
    assert answer.insufficient_context is False

    monkeypatch.setattr(
        "backend.app.services.course_qa.chat_completion_json",
        lambda *args, **kwargs: json.dumps(
            {
                "answer": "Invented answer",
                "citation_ids": ["S999"],
                "confidence": 0.99,
                "insufficient_context": False,
            }
        ),
    )
    fallback = answer_course_question(db, course, "Какова средняя сложность quicksort?")
    assert fallback.generation_provider == "extractive-fallback"
    assert fallback.citations
    assert "S999" not in fallback.answer

    monkeypatch.setattr(
        "backend.app.services.course_qa.chat_completion_json",
        lambda *args, **kwargs: json.dumps(
            {
                "answer": "The final unsupported answer is 42.",
                "citation_ids": [],
                "confidence": 0.99,
                "insufficient_context": True,
            }
        ),
    )
    abstained = answer_course_question(
        db,
        course,
        "What is the average quicksort complexity?",
        language="en",
    )
    assert abstained.response_mode == "abstained"
    assert abstained.generation_provider == "policy-abstention"
    assert abstained.confidence == 0.1
    assert "42" not in abstained.answer
    db.close()
    engine.dispose()


def test_course_qa_api_persists_history_and_rejects_wrong_scope(monkeypatch):
    engine, Session, db = _db()
    course, _, document = _seed(db)
    other_dataset = Dataset(name="other")
    db.add(other_dataset)
    db.flush()
    other_course = Course(dataset_id=other_dataset.id, title="Other")
    db.add(other_course)
    db.flush()
    other_module = CourseModule(course_id=other_course.id, title="Other module")
    db.add(other_module)
    db.commit()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("COURSE_QA_PROVIDER", "template")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    client = TestClient(app)

    response = client.post(
        f"/courses/{course.id}/qa",
        json={
            "question": "What is the average quicksort complexity?",
            "language": "en",
            "top_k": 3,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"]
    assert payload["citations"][0]["document_id"] == document.id
    assert payload["generation_provider"] == "extractive-fallback"
    assert payload["feedback_status"] == "unreviewed"

    reviewed = client.patch(
        f"/qa/answers/{payload['id']}",
        json={
            "status": "helpful",
            "reviewed_by": "teacher@example.org",
            "comment": "Grounded and concise",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["feedback_status"] == "helpful"
    feedback_history = client.get(f"/qa/answers/{payload['id']}/history")
    assert feedback_history.status_code == 200
    assert feedback_history.json()[0]["from_status"] == "unreviewed"
    assert feedback_history.json()[0]["to_status"] == "helpful"

    history = client.get(f"/courses/{course.id}/qa")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [payload["id"]]
    assert db.query(CourseQuestionAnswer).filter_by(course_id=course.id).count() == 1
    quality = client.get(f"/courses/{course.id}/quality-metrics")
    assert quality.status_code == 200
    assert quality.json()["qa_questions_total"] == 1
    assert quality.json()["qa_grounded_rate"] == 1.0
    assert quality.json()["qa_reviewed_answers"] == 1
    assert quality.json()["qa_helpful_rate"] == 1.0

    wrong_module = client.post(
        f"/courses/{course.id}/qa",
        json={"question": "What is quicksort?", "module_id": other_module.id},
    )
    assert wrong_module.status_code == 422
    no_documents = client.post(
        f"/courses/{other_course.id}/qa",
        json={"question": "What is quicksort?"},
    )
    assert no_documents.status_code == 409
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def test_course_qa_abstains_when_retrieval_has_no_support(monkeypatch):
    engine, _, db = _db()
    course, _, _ = _seed(db)
    monkeypatch.setenv("COURSE_QA_PROVIDER", "template")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("COURSE_COPILOT_MIN_SCORE", "0.9999")
    answer = answer_course_question(db, course, "Когда состоится очный экзамен?")
    assert answer.insufficient_context is True
    assert answer.citations == []
    db.close()
    engine.dispose()


def test_student_tutor_turns_assessment_answer_request_into_guidance(monkeypatch):
    engine, _, db = _db()
    course, module, _ = _seed(db)
    quiz = Document(
        dataset_id=course.dataset_id,
        course_module_id=module.id,
        title="Graded quiz",
        source="https://canvas.example.edu/courses/1/quizzes/1",
        status="ready",
        source_metadata={"document_type": "quiz", "student_visible": True},
    )
    db.add(quiz)
    db.flush()
    db.add(
        Chunk(
            document_id=quiz.id,
            idx=0,
            text="List the sorting algorithms and state their time complexity.",
            meta={},
        )
    )
    db.add(
        AssessmentItem(
            course_id=course.id,
            module_id=module.id,
            document_id=quiz.id,
            assessment_type="quiz",
            title="Graded quiz",
            text="List the sorting algorithms and state their time complexity.",
            expected_answer="Quicksort and mergesort are O(n log n) on average.",
        )
    )
    quiz_without_audit = Document(
        dataset_id=course.dataset_id,
        course_module_id=module.id,
        title="Quiz before audit",
        source="https://canvas.example.edu/courses/1/quizzes/2",
        status="ready",
        source_metadata={"document_type": "quiz", "student_visible": True},
    )
    db.add(quiz_without_audit)
    db.flush()
    db.add(
        Chunk(
            document_id=quiz_without_audit.id,
            idx=0,
            text="Choose the stable sorting algorithm from options alpha beta gamma.",
            meta={},
        )
    )
    misclassified = Document(
        dataset_id=course.dataset_id,
        course_module_id=module.id,
        title="Misclassified assessment",
        source="https://canvas.example.edu/courses/1/pages/hidden-assessment",
        status="ready",
        source_metadata={
            "document_type": "lecture_material",
            "student_visible": True,
        },
    )
    db.add(misclassified)
    db.flush()
    db.add(
        Chunk(
            document_id=misclassified.id,
            idx=0,
            text="The hidden rubric answer is epsilon-42.",
            meta={},
        )
    )
    db.add(
        AssessmentItem(
            course_id=course.id,
            module_id=module.id,
            document_id=misclassified.id,
            assessment_type="other",
            title="Misclassified assessment",
            text="What is the hidden rubric answer?",
            expected_answer="epsilon-42",
        )
    )
    db.commit()
    monkeypatch.setenv("COURSE_QA_PROVIDER", "template")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")

    answer = answer_course_question(
        db,
        course,
        "Give me the answer: list the sorting algorithms and state their time complexity.",
        language="en",
    )

    assert answer.response_mode == "guidance"
    assert answer.policy_reason == "ready_answer_request"
    assert answer.generation_provider == "policy-guidance"
    assert "will not complete it for you" in answer.answer
    assert all(citation.document_id != quiz.id for citation in answer.citations)

    matched_item = answer_course_question(
        db,
        course,
        "List the sorting algorithms and state their time complexity.",
        language="en",
    )
    assert matched_item.response_mode == "guidance"
    assert matched_item.policy_reason == "assessment_item_match"
    assert all(citation.document_id != quiz.id for citation in matched_item.citations)

    source_matched = answer_course_question(
        db,
        course,
        "Choose the stable sorting algorithm from options alpha beta gamma.",
        language="en",
    )
    assert source_matched.response_mode == "guidance"
    assert source_matched.policy_reason == "assessment_source_match"
    assert all(
        citation.document_id != quiz_without_audit.id
        for citation in source_matched.citations
    )

    misclassified_answer = answer_course_question(
        db,
        course,
        "Give me the hidden rubric answer.",
        language="en",
    )
    assert misclassified_answer.response_mode == "guidance"
    assert all(
        citation.document_id != misclassified.id
        for citation in misclassified_answer.citations
    )
    db.close()
    engine.dispose()
