from __future__ import annotations

from .course_alignment import semantic_tokens


def text_similarity(left: str, right: str) -> float:
    a = semantic_tokens(left)
    b = semantic_tokens(right)
    if not a and not b:
        return 1.0 if left.strip().lower() == right.strip().lower() else 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def extraction_metrics(
    predicted: list[str], expected: list[str], threshold: float = 0.6
) -> dict:
    unmatched = set(range(len(expected)))
    true_positive = 0
    matches = []
    for prediction in predicted:
        candidates = [
            (text_similarity(prediction, expected[index]), index) for index in unmatched
        ]
        if not candidates:
            continue
        score, index = max(candidates)
        if score >= threshold:
            unmatched.remove(index)
            true_positive += 1
            matches.append(
                {
                    "prediction": prediction,
                    "expected": expected[index],
                    "similarity": round(score, 4),
                }
            )
    false_positive = len(predicted) - true_positive
    false_negative = len(expected) - true_positive
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
        "matches": matches,
    }


def exact_label_metrics(predicted: list[str], expected: list[str]) -> dict:
    predicted_set = set(predicted)
    expected_set = set(expected)
    true_positive = len(predicted_set & expected_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(expected_set) if expected_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": true_positive,
        "fp": len(predicted_set - expected_set),
        "fn": len(expected_set - predicted_set),
    }
