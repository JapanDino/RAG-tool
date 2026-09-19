import pytest

from backend.app.services.answer_stream import draft_answer
from backend.app.services.course_quality import redact
from backend.app.routers.portal_imports import module_available


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"citations":[7],"answer":"Часть отве', "Часть отве"),
        ('{"citations":[7],"answer":"строка\\nдве"}', "строка\nдве"),
        ('{"citations":[8],"answer":"Секрет"}', ""),
        ('{"citations":[],"answer":"Выдумка"}', ""),
        ('{"answer":"Без источника"}', ""),
        ('{"citations":[true],"answer":"Нет"}', ""),
    ],
)
def test_draft_requires_valid_citations(raw, expected):
    assert draft_answer(raw, {7}) == expected


def test_redaction_names_and_contacts():
    clean = redact(
        "Меня зовут Иван Петров. John Smith, ivan@example.org, +7 (999) 123-45-67, @ivan_petrov. Почему растениям нужен свет?"
    )
    for value in [
        "Иван",
        "Петров",
        "John",
        "Smith",
        "example.org",
        "999",
        "ivan_petrov",
    ]:
        assert value not in clean
    assert "Почему растениям нужен свет?" in clean


@pytest.mark.parametrize(
    "restriction",
    [
        "prerequisite_module_ids",
        "require_sequential_progress",
        "unlock_at",
        "locked_for_user",
        "assignment_overrides",
    ],
)
def test_module_conditions_fail_closed(restriction):
    assert not module_available({"published": True, restriction: True})
    assert not module_available({"published": False})
    assert module_available({"published": True})
