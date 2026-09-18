from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.base import Base
from backend.app.models.models import (
    Chunk,
    Course,
    CourseMembership,
    CourseModule,
    CourseQaFeedbackEvent,
    CourseQuestionAnswer,
    Dataset,
    Document,
    Organization,
    User,
)
from backend.app.services.learning_gap_aggregation import (
    aggregate_learning_gaps,
    create_intervention_draft,
    review_intervention_draft,
    validate_intervention_evidence,
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


def _course(db):
    organization = Organization(slug="gap-school", name="Gap School")
    dataset = Dataset(name="gap-course")
    db.add_all([organization, dataset])
    db.flush()
    course = Course(
        organization_id=organization.id,
        dataset_id=dataset.id,
        title="Алгоритмы",
        source_type="canvas",
    )
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, title="Сортировки", position=1)
    db.add(module)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        course_module_id=module.id,
        title="Сравнение алгоритмов сортировки",
        source="canvas://courses/1/pages/sorting",
        status="ready",
        source_metadata={"document_type": "lecture_material"},
    )
    db.add(document)
    db.flush()
    chunk = Chunk(
        document_id=document.id,
        idx=0,
        text=(
            "Quicksort и mergesort сравнивают по временной сложности, памяти "
            "и устойчивости на разных наборах данных."
        ),
        meta={},
    )
    db.add(chunk)
    db.commit()
    return organization, course, document, chunk


def _student(db, organization, course, index, *, active=True):
    user = User(
        email=f"student-{index}@gap.test",
        display_name=f"Student {index}",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        CourseMembership(
            organization_id=organization.id,
            course_id=course.id,
            user_id=user.id,
            role="student",
            is_active=active,
        )
    )
    db.flush()
    return user


def _answer(
    db,
    course,
    user,
    index,
    *,
    insufficient=True,
    question="Не понимаю, как сравнить quicksort и mergesort по памяти",
    citations=None,
):
    row = CourseQuestionAnswer(
        course_id=course.id,
        asked_by_user_id=user.id,
        question=question,
        answer="Без достаточной опоры лучше вернуться к материалу курса.",
        citations=citations or [],
        confidence=0.2,
        retrieval_method="hash",
        generation_provider="template",
        generation_model=None,
        insufficient_context=insufficient,
        response_mode="abstained" if insufficient else "answer",
        policy_reason="insufficient_context" if insufficient else None,
        tutor_policy_version=1,
        tutor_answer_style="balanced",
        feedback_status="unreviewed",
        created_at=datetime.now(UTC) - timedelta(days=index),
    )
    db.add(row)
    db.flush()
    return row


def test_three_distinct_students_surface_one_bounded_anchored_candidate():
    engine, db = _db()
    try:
        organization, course, _, _ = _course(db)
        raw_questions = []
        for index in range(3):
            student = _student(db, organization, course, index)
            answer = _answer(db, course, student, index)
            raw_questions.append(answer.question)
        db.commit()

        candidates = aggregate_learning_gaps(db, course)

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.signal_kind == "repeated_unsupported"
        assert candidate.cohort_band == "3–5"
        assert candidate.event_band == "3–5"
        assert candidate.topic_label == "Сравнение алгоритмов сортировки"
        serialized = repr(candidate)
        assert all(question not in serialized for question in raw_questions)
        assert "student-" not in serialized
    finally:
        db.close()
        engine.dispose()


def test_one_student_flood_and_inactive_members_do_not_cross_threshold():
    engine, db = _db()
    try:
        organization, course, _, _ = _course(db)
        one_student = _student(db, organization, course, 1)
        for index in range(6):
            _answer(db, course, one_student, index)
        inactive = _student(db, organization, course, 2, active=False)
        _answer(db, course, inactive, 1)
        db.commit()

        assert aggregate_learning_gaps(db, course) == []
    finally:
        db.close()
        engine.dispose()


def test_latest_owner_unhelpful_feedback_qualifies_without_exposing_comment():
    engine, db = _db()
    try:
        organization, course, document, chunk = _course(db)
        private_comments = []
        for index in range(3):
            student = _student(db, organization, course, index)
            answer = _answer(
                db,
                course,
                student,
                index,
                insufficient=False,
                citations=[
                    {
                        "source_id": "S1",
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                        "quote": chunk.text,
                    }
                ],
            )
            comment = f"private comment {index}"
            private_comments.append(comment)
            db.add(
                CourseQaFeedbackEvent(
                    answer_id=answer.id,
                    course_id=course.id,
                    reviewed_by_user_id=student.id,
                    from_status="unreviewed",
                    to_status="unhelpful",
                    reviewed_by=student.email,
                    comment=comment,
                )
            )
        db.commit()

        candidate = aggregate_learning_gaps(db, course)[0]

        assert candidate.signal_kind == "low_helpfulness"
        assert all(comment not in repr(candidate) for comment in private_comments)
    finally:
        db.close()
        engine.dispose()


def test_unanchored_questions_remain_hidden():
    engine, db = _db()
    try:
        organization, course, _, _ = _course(db)
        for index in range(3):
            student = _student(db, organization, course, index)
            _answer(
                db,
                course,
                student,
                index,
                question="Как выбрать масло для двигателя автомобиля?",
            )
        db.commit()

        assert aggregate_learning_gaps(db, course) == []
    finally:
        db.close()
        engine.dispose()


def test_distinct_chunks_in_one_document_do_not_merge_into_a_repeated_gap():
    engine, db = _db()
    try:
        organization, course, document, first_chunk = _course(db)
        chunks = [
            first_chunk,
            Chunk(
                document_id=document.id,
                idx=1,
                text="Insertion sort builds a sorted prefix one item at a time.",
                meta={},
            ),
            Chunk(
                document_id=document.id,
                idx=2,
                text="Counting sort uses a bounded range of integer keys.",
                meta={},
            ),
        ]
        db.add_all(chunks[1:])
        db.flush()
        for index, chunk in enumerate(chunks):
            student = _student(db, organization, course, index)
            _answer(
                db,
                course,
                student,
                index,
                citations=[
                    {
                        "source_id": "S1",
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                        "quote": chunk.text,
                    }
                ],
            )
        db.commit()

        assert aggregate_learning_gaps(db, course) == []
    finally:
        db.close()
        engine.dispose()


def test_rolling_window_excludes_old_and_future_events():
    engine, db = _db()
    try:
        organization, course, _, _ = _course(db)
        now = datetime(2026, 8, 3, 12, tzinfo=UTC)
        dates = [
            now - timedelta(days=1),
            now - timedelta(days=30, seconds=1),
            now + timedelta(seconds=1),
        ]
        answers = []
        for index, created_at in enumerate(dates):
            student = _student(db, organization, course, index)
            answer = _answer(db, course, student, index)
            answer.created_at = created_at
            answers.append(answer)
        db.commit()

        assert aggregate_learning_gaps(db, course, now=now) == []

        answers[1].created_at = now - timedelta(days=29)
        answers[2].created_at = now - timedelta(seconds=1)
        db.commit()
        candidate = aggregate_learning_gaps(db, course, now=now)[0]
        assert candidate.event_count == 3
        assert candidate.window_ended_at == now
        assert candidate.window_started_at == now - timedelta(days=30)
    finally:
        db.close()
        engine.dispose()


def test_public_confidence_does_not_change_with_exact_private_counts():
    engine, db = _db()
    try:
        organization, course, _, _ = _course(db)
        for index in range(3):
            student = _student(db, organization, course, index)
            _answer(db, course, student, index)
        db.commit()
        first = aggregate_learning_gaps(db, course)[0]

        for index in range(3, 5):
            student = _student(db, organization, course, index)
            _answer(db, course, student, index)
        db.commit()
        second = aggregate_learning_gaps(db, course)[0]

        assert first.confidence == second.confidence == 0.68
    finally:
        db.close()
        engine.dispose()


def test_intervention_review_records_edit_distance_and_latency():
    engine, db = _db()
    try:
        organization, course, _, _ = _course(db)
        for index in range(3):
            student = _student(db, organization, course, index)
            _answer(db, course, student, index)
        reviewer = User(
            email="instructor@gap.test",
            display_name="Instructor",
            is_active=True,
        )
        db.add(reviewer)
        db.commit()
        candidate = aggregate_learning_gaps(db, course)[0]
        draft = create_intervention_draft(db, course, candidate)
        db.commit()
        db.refresh(draft)
        assert validate_intervention_evidence(db, course, draft)

        reviewed = review_intervention_draft(
            db,
            draft,
            reviewer_user_id=reviewer.id,
            status="accepted",
            content=draft.content + "\n\nПроверено преподавателем.",
            now=datetime.now(UTC) + timedelta(minutes=2),
        )
        db.commit()

        assert reviewed.status == "accepted"
        assert reviewed.version == 2
        assert reviewed.edit_distance_ratio > 0
        assert reviewed.decision_latency_seconds >= 120
        assert reviewed.reviewed_by_user_id == reviewer.id
    finally:
        db.close()
        engine.dispose()
