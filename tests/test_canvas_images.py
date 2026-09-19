import pytest
from material_image_fixtures import png

from backend.app.services import canvas_images as ci


def metadata(**changes):
    return {
        "id": 7,
        "url": "https://canvas.test/files/7/download",
        "content-type": "image/png",
        "size": 1000,
        "updated_at": "2026-01-01T00:00:00Z",
        "hidden": False,
        "locked": False,
        **changes,
    }


def test_course_images_preserve_context_and_reject_external_files(monkeypatch):
    monkeypatch.setenv("CANVAS_URL", "https://canvas.test")
    calls = []

    def get_file(course, file_id):
        calls.append((course, file_id))
        return metadata()

    monkeypatch.setattr(ci.canvas_client, "get_file", get_file)
    monkeypatch.setattr(ci, "download_image", lambda _: png())
    body = '<p>Энергия света</p><figure><img src="/courses/123/files/7/preview" alt="АТФ"/><figcaption>Две фазы</figcaption></figure>'
    body += '<img src="https://evil.test/files/7"/><img src="/courses/999/files/7/preview"/>'
    result = ci.extract_canvas_images(body, 123)
    assert len(result.images) == 1 and result.skipped == 2
    assert calls == [(123, 7)]
    assert result.images[0].canvas_file_id == 7
    assert "Энергия света" in result.images[0].context
    assert result.images[0].caption == "АТФ"


@pytest.mark.parametrize(
    "changes",
    [
        {"hidden": True},
        {"locked": True},
        {"locked_for_user": True},
        {"unlock_at": "2099-01-01T00:00:00Z"},
        {"lock_at": "2020-01-01T00:00:00Z"},
        {"unlock_at": "invalid"},
        {"visibility_level": "admins"},
        {"updated_at": None},
    ],
)
def test_restricted_files_are_not_imported(changes):
    assert not ci.file_available(metadata(**changes))


def test_download_redirects_are_allowlisted_and_never_leak_canvas_token(monkeypatch):
    monkeypatch.setenv("CANVAS_URL", "https://canvas.test")
    monkeypatch.setenv("CANVAS_TOKEN", "synthetic-canvas-token")
    monkeypatch.setenv("CANVAS_FILE_ORIGINS", "https://cdn.test")
    calls = []

    class Response:
        def __init__(self, redirect):
            self.status_code = 302 if redirect else 200
            self.headers = (
                {"Location": "https://cdn.test/image.png"} if redirect else {}
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b"image"

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(len(calls) == 1)

    monkeypatch.setattr(ci.requests, "get", get)
    assert ci.download_image("https://canvas.test/files/7/download") == b"image"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer synthetic-canvas-token"
    assert calls[1][1]["headers"] == {}
    assert all(not kwargs["allow_redirects"] for _, kwargs in calls)
    with pytest.raises(ValueError):
        ci.download_image("http://127.0.0.1/private")
    assert len(calls) == 2
    monkeypatch.setenv("CANVAS_FILE_ORIGINS", "")
    calls.clear()
    with pytest.raises(ValueError):
        ci.download_image("https://canvas.test/files/7/download")
    assert len(calls) == 1
