"""Tests for _hamming_loss, _f1_micro, _f1_macro from evaluate.py router."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.routers.evaluate import _hamming_loss, _f1_micro, _f1_macro, _vectorize
from backend.app.utils.bloom import LEVEL_ORDER


# ---------------------------------------------------------------------------
# _vectorize
# ---------------------------------------------------------------------------

def test_vectorize_all_zeros_for_unknown():
    vec = _vectorize(["nonexistent_level"])
    assert vec == [0] * 6


def test_vectorize_single_level():
    vec = _vectorize(["remember"])
    assert vec[LEVEL_ORDER.index("remember")] == 1
    assert sum(vec) == 1


def test_vectorize_multiple_levels():
    vec = _vectorize(["analyze", "evaluate"])
    assert vec[LEVEL_ORDER.index("analyze")] == 1
    assert vec[LEVEL_ORDER.index("evaluate")] == 1
    assert sum(vec) == 2


# ---------------------------------------------------------------------------
# _hamming_loss
# ---------------------------------------------------------------------------

def test_hamming_loss_perfect():
    y = [[1, 0, 0, 1, 0, 0], [0, 1, 0, 0, 0, 0]]
    assert _hamming_loss(y, y) == 0.0


def test_hamming_loss_all_wrong():
    y_true = [[1, 1, 1, 1, 1, 1]]
    y_pred = [[0, 0, 0, 0, 0, 0]]
    assert _hamming_loss(y_true, y_pred) == 1.0


def test_hamming_loss_half_wrong():
    y_true = [[1, 0, 1, 0, 1, 0]]
    y_pred = [[0, 0, 1, 0, 1, 0]]  # 1 error out of 6
    loss = _hamming_loss(y_true, y_pred)
    assert abs(loss - 1 / 6) < 1e-6


def test_hamming_loss_empty():
    assert _hamming_loss([], []) == 0.0


# ---------------------------------------------------------------------------
# _f1_micro
# ---------------------------------------------------------------------------

def test_f1_micro_perfect():
    y = [[1, 0, 1, 0, 0, 0], [0, 1, 0, 0, 0, 0]]
    assert _f1_micro(y, y) == 1.0


def test_f1_micro_no_overlap():
    y_true = [[1, 0, 0, 0, 0, 0]]
    y_pred = [[0, 1, 0, 0, 0, 0]]
    assert _f1_micro(y_true, y_pred) == 0.0


def test_f1_micro_partial():
    y_true = [[1, 1, 0, 0, 0, 0]]
    y_pred = [[1, 0, 0, 0, 0, 0]]
    # tp=1, fp=0, fn=1 → F1 = 2*1/(2+0+1) = 2/3
    f1 = _f1_micro(y_true, y_pred)
    assert abs(f1 - 2 / 3) < 1e-6


def test_f1_micro_empty():
    assert _f1_micro([], []) == 0.0


# ---------------------------------------------------------------------------
# _f1_macro
# ---------------------------------------------------------------------------

def test_f1_macro_perfect():
    # One example per level so every level has TP=1, FP=0, FN=0 → F1=1.0 for all.
    y = [
        [1, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1],
    ]
    assert _f1_macro(y, y) == 1.0


def test_f1_macro_all_zeros():
    y_true = [[0, 0, 0, 0, 0, 0]]
    y_pred = [[0, 0, 0, 0, 0, 0]]
    # All TP/FP/FN = 0 → each level f1 = 0
    assert _f1_macro(y_true, y_pred) == 0.0


def test_f1_macro_empty():
    assert _f1_macro([], []) == 0.0


def test_f1_macro_leq_f1_micro_on_imbalanced():
    """Macro F1 ≤ micro F1 when rare classes have low recall."""
    y_true = [[1, 0, 0, 0, 0, 1]] * 10 + [[0, 1, 0, 0, 0, 0]]
    y_pred = [[1, 0, 0, 0, 0, 0]] * 10 + [[0, 0, 0, 0, 0, 0]]
    micro = _f1_micro(y_true, y_pred)
    macro = _f1_macro(y_true, y_pred)
    # Both should be valid floats in [0,1]
    assert 0.0 <= micro <= 1.0
    assert 0.0 <= macro <= 1.0
