def test_import_enqueue():
    from backend.app.tasks.queue import enqueue_or_mark  # noqa
    assert callable(enqueue_or_mark)
