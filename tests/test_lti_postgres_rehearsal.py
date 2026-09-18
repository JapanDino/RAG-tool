import pytest

pytest.importorskip("sqlalchemy")

from scripts.rehearse_lti_postgres import rehearsal_database_url


@pytest.mark.parametrize(
    "database_url",
    (
        "",
        "sqlite+pysqlite:///:memory:",
        "postgresql+psycopg://user@localhost/rag_db",
        "postgresql+psycopg://user@localhost/production",
        "postgresql+psycopg://user@localhost/latest",
        "postgresql+psycopg://user@localhost/contest_production",
    ),
)
def test_rehearsal_database_guard_rejects_unsafe_targets(monkeypatch, database_url):
    monkeypatch.setenv("M05_REHEARSAL_DISPOSABLE", "1")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError):
        rehearsal_database_url()


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql+psycopg://user@localhost/rag_m05_rehearsal",
        "postgresql+psycopg://user@localhost/rag_lti_test",
    ),
)
def test_rehearsal_database_guard_allows_only_marked_postgres(
    monkeypatch, database_url
):
    monkeypatch.setenv("M05_REHEARSAL_DISPOSABLE", "1")
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert rehearsal_database_url() == database_url


def test_rehearsal_database_guard_requires_disposable_confirmation(monkeypatch):
    monkeypatch.delenv("M05_REHEARSAL_DISPOSABLE", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user@localhost/rag_m05_rehearsal",
    )

    with pytest.raises(RuntimeError):
        rehearsal_database_url()
