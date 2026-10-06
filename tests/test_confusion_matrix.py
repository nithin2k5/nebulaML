"""Tests for the full confusion matrix over an evaluation split.

`class_confusion` already ranks the pairs that collide. This covers the matrix
that complements it, and in particular its bookkeeping: every ground-truth box
and every prediction must land in exactly one cell. Pairing boxes by label
instead of class-agnostically breaks that — a mislabelled object gets counted
twice, as a miss of its real class and an invention of the predicted one — and
the row/column sum tests below are what catch it.

The fixture image is 100x100 with two ground-truth boxes:
    class 0 ("cat") at [10, 10, 50, 50]
    class 1 ("dog") at [60, 60, 90, 90]
"""

import numpy as np
import pytest

from app.services.error_analysis import confusion_matrix

CLASS_NAMES = {0: "cat", 1: "dog"}
N_CLASSES = 2
BACKGROUND = 2

GT = {
    "boxes": np.array([[10, 10, 50, 50], [60, 60, 90, 90]], dtype=np.float32),
    "labels": np.array([0, 1], dtype=int),
}


def _pred(rows):
    """rows: (x1, y1, x2, y2, score, label)."""
    if not rows:
        return {
            "boxes": np.zeros((0, 4), np.float32),
            "scores": np.zeros(0, np.float32),
            "labels": np.zeros(0, int),
        }
    arr = np.asarray(rows, dtype=np.float32)
    return {
        "boxes": arr[:, :4].copy(),
        "scores": arr[:, 4].copy(),
        "labels": arr[:, 5].astype(int),
    }


def _matrix(pred_rows, targets=None, **kwargs):
    predictions = [_pred(rows) for rows in pred_rows]
    targets = targets or [GT] * len(pred_rows)
    return np.asarray(
        confusion_matrix(predictions, targets, N_CLASSES, **kwargs)["matrix"]
    )


# ── Shape ────────────────────────────────────────────────────────────────────


def test_matrix_has_a_background_row_and_column():
    result = confusion_matrix([_pred([])], [GT], N_CLASSES)
    assert result["background_index"] == BACKGROUND
    assert result["n_classes"] == N_CLASSES
    assert np.asarray(result["matrix"]).shape == (N_CLASSES + 1, N_CLASSES + 1)


# ── The reason it pairs class-agnostically ───────────────────────────────────


def test_a_mislabelled_object_lands_off_the_diagonal_once():
    """A dog called 'cat' is [dog][cat] — not a missed dog plus an invented cat."""
    matrix = _matrix([[(60, 60, 90, 90, 0.9, 0)]])

    assert matrix[1][0] == 1                 # actual dog, predicted cat
    assert matrix[1][BACKGROUND] == 0        # and NOT also counted as missed
    assert matrix[BACKGROUND][0] == 0        # nor as an invented cat
    # The cat ground truth is genuinely missed, and that is the only other cell.
    assert matrix[0][BACKGROUND] == 1
    assert matrix.sum() == 2


def test_correct_detections_sit_on_the_diagonal():
    matrix = _matrix([[(10, 10, 50, 50, 0.9, 0), (60, 60, 90, 90, 0.8, 1)]])
    assert matrix[0][0] == 1
    assert matrix[1][1] == 1
    assert matrix.sum() == 2


# ── Bookkeeping ──────────────────────────────────────────────────────────────


def test_rows_sum_to_ground_truth_and_columns_to_predictions():
    """The invariant that pairing by label would break."""
    matrix = _matrix([
        [
            (10, 10, 50, 50, 0.9, 0),      # correct cat
            (60, 60, 90, 90, 0.8, 0),      # dog called cat
            (0, 95, 5, 100, 0.7, 1),       # invented dog
        ],
        [(10, 10, 50, 50, 0.9, 0)],        # correct cat, dog missed
    ])

    # 2 cats and 2 dogs of ground truth across the two images.
    assert matrix[0].sum() == 2
    assert matrix[1].sum() == 2
    # 4 predictions, all in real-class columns.
    assert matrix[:, :N_CLASSES].sum() == 4
    # Every GT box plus the one invention.
    assert matrix.sum() == 5

    assert matrix[0][0] == 2                 # both cats found
    assert matrix[1][0] == 1                 # one dog called a cat
    assert matrix[1][BACKGROUND] == 1        # the other dog missed
    assert matrix[BACKGROUND][1] == 1        # the invented dog


def test_a_duplicate_is_counted_as_a_spurious_box_not_a_second_hit():
    """Two boxes on one object: one pairs, the other has no object left."""
    matrix = _matrix([[
        (10, 10, 50, 50, 0.9, 0),
        (11, 11, 51, 51, 0.8, 0),
    ]])
    assert matrix[0][0] == 1                 # the object, found once
    assert matrix[BACKGROUND][0] == 1        # the surplus box
    assert matrix[1][BACKGROUND] == 1        # the dog, still missed


# ── Edges ────────────────────────────────────────────────────────────────────


def test_no_predictions_puts_every_box_in_the_background_column():
    matrix = _matrix([[]])
    assert matrix[0][BACKGROUND] == 1
    assert matrix[1][BACKGROUND] == 1
    assert matrix[:, :N_CLASSES].sum() == 0


def test_predictions_on_an_unlabelled_image_are_all_background_row():
    empty_gt = {"boxes": np.zeros((0, 4), np.float32), "labels": np.zeros(0, int)}
    matrix = _matrix([[(1, 1, 9, 9, 0.9, 0), (20, 20, 30, 30, 0.8, 1)]], targets=[empty_gt])
    assert matrix[BACKGROUND][0] == 1
    assert matrix[BACKGROUND][1] == 1
    assert matrix.sum() == 2


def test_an_out_of_range_label_falls_into_background():
    """A class id the dataset does not define cannot occupy a real column."""
    matrix = _matrix([[(10, 10, 50, 50, 0.9, 7)]])
    assert matrix[0][BACKGROUND] == 1        # paired with the cat, labelled unknown
    assert matrix[:, :N_CLASSES].sum() == 0


def test_an_empty_split_gives_an_all_zero_matrix():
    matrix = np.asarray(confusion_matrix([], [], N_CLASSES)["matrix"])
    assert matrix.sum() == 0


# ── Thresholds ───────────────────────────────────────────────────────────────


def test_predictions_below_the_operating_point_are_excluded():
    """The matrix describes one operating point, like precision and recall."""
    rows = [[(10, 10, 50, 50, 0.3, 0)]]
    assert _matrix(rows, conf_threshold=0.25)[0][0] == 1
    # Raised above the box's confidence, the detection is no longer made.
    strict = _matrix(rows, conf_threshold=0.5)
    assert strict[0][0] == 0
    assert strict[0][BACKGROUND] == 1


def test_a_loose_box_fails_to_pair_at_a_strict_iou():
    # A 25x25 box inside the cat's 40x40: IoU 625/1600 = 0.39, so it pairs at
    # 0.3 and not at 0.5.
    rows = [[(10, 10, 35, 35, 0.9, 0)]]
    assert _matrix(rows, iou_threshold=0.3)[0][0] == 1

    strict = _matrix(rows, iou_threshold=0.5)
    assert strict[0][0] == 0
    assert strict[0][BACKGROUND] == 1        # the cat, unfound
    assert strict[BACKGROUND][0] == 1        # the box, unpaired


def test_highest_confidence_prediction_pairs_first():
    """Pairing order must be deterministic, best guess first."""
    matrix = _matrix([[
        (12, 12, 52, 52, 0.95, 0),           # looser, but more confident
        (10, 10, 50, 50, 0.60, 1),           # exact, lower score, wrong label
    ]])
    # The confident box claims the cat; the exact one is left over.
    assert matrix[0][0] == 1
    assert matrix[BACKGROUND][1] == 1


@pytest.mark.parametrize("n_classes", [1, 2, 5])
def test_matrix_sizes_with_the_class_count(n_classes):
    result = confusion_matrix([_pred([])], [GT], n_classes)
    assert np.asarray(result["matrix"]).shape == (n_classes + 1, n_classes + 1)
