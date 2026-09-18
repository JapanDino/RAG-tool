from backend.app.services.course_evaluation import (
    exact_label_metrics,
    extraction_metrics,
)


def test_course_audit_evaluation_metrics():
    extraction = extraction_metrics(
        ["Анализировать временную сложность алгоритмов", "Лишняя цель"],
        ["Студент сможет анализировать временную сложность алгоритмов"],
        threshold=0.5,
    )
    assert extraction["tp"] == 1
    assert extraction["fp"] == 1
    assert extraction["fn"] == 0
    assert extraction["recall"] == 1.0

    labels = exact_label_metrics(
        ["objective_without_assessment", "bloom_mismatch"],
        ["objective_without_assessment", "objective_without_material"],
    )
    assert labels == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "tp": 1,
        "fp": 1,
        "fn": 1,
    }
