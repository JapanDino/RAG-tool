from backend.app.services.validation import validate_annotation


def test_validate_annotation_ok():
    ok, err = validate_annotation(
        {"level": "apply", "label": "Apply", "rationale": "ok", "score": 0.9}
    )
    assert ok is True
    assert err is None


def test_validate_annotation_bad_score():
    ok, err = validate_annotation(
        {"level": "apply", "label": "Apply", "rationale": "ok", "score": 1.5}
    )
    assert ok is False
    assert err is not None


def test_validate_annotation_empty_label():
    ok, err = validate_annotation({"level": "apply", "label": "", "rationale": "ok", "score": 0.5})
    assert ok is False
    assert err is not None

