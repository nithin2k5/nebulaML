"""Unit tests for the evaluation matching and error-diagnosis logic.

These cover the parts that are easy to get subtly wrong — match ordering,
the error taxonomy, and the confusion matrix's bookkeeping — on hand-built
arrays, so they need neither a model nor a database.

The fixture image is 100x100 with two ground-truth boxes:
    class 0 at [10, 10, 50, 50]   (top-left)
    class 1 at [60, 60, 90, 90]   (bottom-right)
"""

import numpy as np
import pytest
from app.services.evaluation import (
    build_confusion_matrix,
    classify_image,
    count_outcomes,
    greedy_match,
    gt_to_xyxy,
    predictions_to_arrays,
    threshold_sweep,
)

CLASS_NAMES = ["cat", "dog"]

GT_BOXES = np.array([[10, 10, 50, 50], [60, 60, 90, 90]], dtype=np.float32)
GT_LABELS = np.array([0, 1], dtype=int)


def _preds(rows):
    """rows: (x1, y1, x2, y2, score, label) -> the three prediction arrays."""
    if not rows:
        return (
            np.zeros((0, 4), np.float32),
            np.zeros(0, np.float32),
            np.zeros(0, int),
        )
    arr = np.asarray(rows, dtype=np.float32)
    return arr[:, :4].copy(), arr[:, 4].copy(), arr[:, 5].astype(int)


def _by_type(records):
    counts = {}
    for record in records:
        counts[record["error_type"]] = counts.get(record["error_type"], 0) + 1
    return counts


# ── Conversion ───────────────────────────────────────────────────────────────


def test_gt_to_xyxy_converts_normalized_centre_format():
    boxes = [{"class_id": 3, "bbox_normalized": [0.5, 0.5, 0.2, 0.4]}]
    xyxy, labels = gt_to_xyxy(boxes, 100, 200)
    # cx=50, cy=100, w=20, h=80 in pixels.
    assert xyxy.tolist() == [[40.0, 60.0, 60.0, 140.0]]
    assert labels.tolist() == [3]


def test_gt_to_xyxy_skips_malformed_boxes():
    xyxy, labels = gt_to_xyxy(
        [{"class_id": 0}, {"class_id": 1, "bbox_normalized": [0.1, 0.1]}], 100, 100
    )
    assert len(xyxy) == 0 and len(labels) == 0


def test_gt_to_xyxy_handles_empty():
    xyxy, labels = gt_to_xyxy([], 100, 100)
    assert xyxy.shape == (0, 4)
    assert labels.shape == (0,)


def test_predictions_resolve_classes_by_name_not_by_model_id():
    """A checkpoint trained elsewhere numbers its classes differently."""
    detections = [
        # Model calls this class 7; the version has 'dog' at index 1.
        {"bbox": [1, 2, 3, 4], "confidence": 0.9, "class_id": 7, "class_name": "dog"},
        # A class this version does not define at all.
        {"bbox": [5, 6, 7, 8], "confidence": 0.8, "class_id": 0, "class_name": "giraffe"},
    ]
    boxes, scores, labels = predictions_to_arrays(
        detections, {name: i for i, name in enumerate(CLASS_NAMES)}
    )
    assert boxes.shape == (2, 4)
    assert scores.tolist() == pytest.approx([0.9, 0.8])
    # Resolved by name, and the unknown class becomes -1 so it can only ever
    # be a false positive rather than scoring against whatever sits at its id.
    assert labels.tolist() == [1, -1]


# ── Matching ─────────────────────────────────────────────────────────────────


def test_highest_confidence_prediction_wins_the_match():
    """The best guess gets first refusal, so a duplicate cannot steal it."""
    # Both overlap GT 0; the looser box is the more confident one.
    boxes, scores, labels = _preds([
        (12, 12, 52, 52, 0.95, 0),   # IoU ~0.80, listed first
        (10, 10, 50, 50, 0.60, 0),   # a perfect box, but less confident
    ])
    pred_to_gt, gt_to_pred, _ = greedy_match(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5
    )
    assert pred_to_gt.tolist() == [0, -1]
    assert gt_to_pred[0] == 0


def test_a_ground_truth_box_is_claimed_only_once():
    boxes, scores, labels = _preds([
        (10, 10, 50, 50, 0.9, 0),
        (10, 10, 50, 50, 0.8, 0),
        (10, 10, 50, 50, 0.7, 0),
    ])
    pred_to_gt, _, _ = greedy_match(boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5)
    assert sorted(pred_to_gt.tolist()) == [-1, -1, 0]


def test_class_aware_match_rejects_the_wrong_label():
    """A perfectly placed box with the wrong class is not a match."""
    boxes, scores, labels = _preds([(10, 10, 50, 50, 0.9, 1)])
    pred_to_gt, _, _ = greedy_match(boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5)
    assert pred_to_gt.tolist() == [-1]

    # Class-agnostically it does match — that is what the confusion matrix uses.
    pred_to_gt, _, _ = greedy_match(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5, class_agnostic=True
    )
    assert pred_to_gt.tolist() == [0]


def test_match_handles_empty_sides():
    empty_b, empty_s, empty_l = _preds([])
    pred_to_gt, gt_to_pred, _ = greedy_match(
        empty_b, empty_s, empty_l, GT_BOXES, GT_LABELS, 0.5
    )
    assert len(pred_to_gt) == 0
    assert gt_to_pred.tolist() == [-1, -1]

    boxes, scores, labels = _preds([(10, 10, 50, 50, 0.9, 0)])
    pred_to_gt, gt_to_pred, _ = greedy_match(
        boxes, scores, labels, np.zeros((0, 4), np.float32), np.zeros(0, int), 0.5
    )
    assert pred_to_gt.tolist() == [-1]
    assert len(gt_to_pred) == 0


def test_count_outcomes_counts_tp_fp_fn():
    boxes, scores, labels = _preds([
        (10, 10, 50, 50, 0.9, 0),       # matches GT 0
        (0, 90, 5, 100, 0.8, 0),        # invented
    ])
    assert count_outcomes(boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5) == (1, 1, 1)


# ── Error taxonomy ───────────────────────────────────────────────────────────


def test_every_error_type_is_diagnosed():
    boxes, scores, labels = _preds([
        (10, 10, 50, 50, 0.90, 0),   # exact match for GT 0      -> correct
        (11, 11, 51, 51, 0.80, 0),   # same object again         -> duplicate
        (60, 60, 70, 70, 0.70, 1),   # right class, IoU ~0.11    -> poor_localization
        (60, 60, 90, 90, 0.60, 0),   # GT 1's box, wrong label   -> wrong_class
        (0, 95, 5, 100, 0.50, 0),    # nothing there             -> background
    ])
    records = classify_image(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5, CLASS_NAMES
    )

    assert _by_type(records) == {
        "correct": 1,
        "duplicate": 1,
        "poor_localization": 1,
        "wrong_class": 1,
        "background": 1,
        # GT 1 is never matched at IoU 0.5, so it is also reported missed.
        "missed": 1,
    }

    outcomes = [r["outcome"] for r in records]
    assert outcomes.count("tp") == 1
    assert outcomes.count("fp") == 4
    assert outcomes.count("fn") == 1


def test_correct_record_carries_both_boxes_and_the_iou():
    boxes, scores, labels = _preds([(10, 10, 50, 50, 0.9, 0)])
    record = classify_image(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5, CLASS_NAMES
    )[0]
    assert record["outcome"] == "tp"
    assert record["error_type"] == "correct"
    assert record["iou"] == pytest.approx(1.0)
    assert record["pred_class_name"] == "cat"
    assert record["gt_class_name"] == "cat"
    assert record["box"] == [10.0, 10.0, 50.0, 50.0]
    assert record["gt_box"] == [10.0, 10.0, 50.0, 50.0]


def test_wrong_class_record_blames_the_object_it_actually_found():
    boxes, scores, labels = _preds([(60, 60, 90, 90, 0.9, 0)])
    records = classify_image(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5, CLASS_NAMES
    )
    fp = next(r for r in records if r["outcome"] == "fp")
    assert fp["error_type"] == "wrong_class"
    assert fp["pred_class_name"] == "cat"   # what the model said
    assert fp["gt_class_name"] == "dog"     # what was actually there
    assert fp["iou"] == pytest.approx(1.0)


def test_unknown_class_prediction_is_a_false_positive():
    """A class the version does not define cannot be correct."""
    boxes, scores, labels = _preds([(10, 10, 50, 50, 0.9, -1)])
    records = classify_image(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5, CLASS_NAMES
    )
    fp = next(r for r in records if r["outcome"] == "fp")
    assert fp["outcome"] == "fp"
    assert fp["pred_class_name"] is None


def test_no_predictions_means_everything_is_missed():
    boxes, scores, labels = _preds([])
    records = classify_image(
        boxes, scores, labels, GT_BOXES, GT_LABELS, 0.5, CLASS_NAMES
    )
    assert _by_type(records) == {"missed": 2}
    assert all(r["box"] is None for r in records)


def test_predictions_on_an_empty_image_are_all_background():
    boxes, scores, labels = _preds([(1, 1, 9, 9, 0.9, 0), (20, 20, 30, 30, 0.8, 1)])
    records = classify_image(
        boxes, scores, labels, np.zeros((0, 4), np.float32), np.zeros(0, int),
        0.5, CLASS_NAMES,
    )
    assert _by_type(records) == {"background": 2}


# ── Confusion matrix ─────────────────────────────────────────────────────────


def _item(rows, gt_boxes=GT_BOXES, gt_labels=GT_LABELS):
    boxes, scores, labels = _preds(rows)
    return {
        "boxes": boxes, "scores": scores, "labels": labels,
        "gt_boxes": gt_boxes, "gt_labels": gt_labels,
    }


def test_confusion_matrix_puts_a_mislabelled_object_off_the_diagonal():
    """A dog called 'cat' belongs at [dog][cat], not as a miss plus an invention."""
    matrix = build_confusion_matrix(
        [_item([(60, 60, 90, 90, 0.9, 0)])], len(CLASS_NAMES), 0.5
    )["matrix"]
    background = len(CLASS_NAMES)
    assert matrix[1][0] == 1               # GT dog, predicted cat
    assert matrix[1][background] == 0      # and NOT also counted as missed
    assert matrix[background][0] == 0      # nor as an invented cat


def test_confusion_matrix_counts_each_box_exactly_once():
    """Rows must sum to the ground truth per class, columns to the predictions."""
    items = [
        _item([
            (10, 10, 50, 50, 0.9, 0),    # correct cat
            (60, 60, 90, 90, 0.8, 0),    # dog called cat
            (0, 95, 5, 100, 0.7, 1),     # invented dog
        ]),
        _item([(10, 10, 50, 50, 0.9, 0)]),   # correct cat, dog missed
    ]
    result = build_confusion_matrix(items, len(CLASS_NAMES), 0.5)
    matrix = np.asarray(result["matrix"])

    # 2 cats and 2 dogs of ground truth, 4 predictions in total.
    assert matrix[0].sum() == 2
    assert matrix[1].sum() == 2
    assert matrix[:, :len(CLASS_NAMES)].sum() == 4
    assert matrix.sum() == 2 + 2 + 1       # every GT box, plus the invented one

    background = result["background_index"]
    assert matrix[0][0] == 2               # both cats found
    assert matrix[1][0] == 1               # one dog called a cat
    assert matrix[1][background] == 1      # the other dog missed
    assert matrix[background][1] == 1      # the invented dog


def test_confusion_matrix_sends_unknown_classes_to_background():
    matrix = build_confusion_matrix(
        [_item([(10, 10, 50, 50, 0.9, -1)])], len(CLASS_NAMES), 0.5
    )["matrix"]
    background = len(CLASS_NAMES)
    # Matched a real cat class-agnostically, but the label is not in the schema.
    assert matrix[0][background] == 1


# ── Threshold sweep ──────────────────────────────────────────────────────────


def test_sweep_recall_falls_as_confidence_rises():
    items = [_item([
        (10, 10, 50, 50, 0.90, 0),
        (60, 60, 90, 90, 0.30, 1),
    ])]
    sweep = threshold_sweep(items, 0.5, thresholds=[0.1, 0.5, 0.95])
    recalls = [entry["recall"] for entry in sweep]
    assert recalls == sorted(recalls, reverse=True)

    assert sweep[0]["tp"] == 2 and sweep[0]["fn"] == 0    # both kept
    assert sweep[1]["tp"] == 1 and sweep[1]["fn"] == 1    # the 0.30 box dropped
    assert sweep[2]["tp"] == 0 and sweep[2]["fn"] == 2    # nothing left


def test_sweep_drops_false_positives_as_confidence_rises():
    items = [_item([
        (10, 10, 50, 50, 0.90, 0),      # a real cat
        (0, 95, 5, 100, 0.20, 0),       # a low-confidence invention
    ])]
    low, high = threshold_sweep(items, 0.5, thresholds=[0.1, 0.5])
    assert low["fp"] == 1
    assert high["fp"] == 0
    assert high["precision"] == pytest.approx(1.0)


def test_sweep_reports_every_requested_level():
    sweep = threshold_sweep([_item([])], 0.5)
    assert len(sweep) == 19
    assert all(entry["tp"] == 0 and entry["fn"] == 2 for entry in sweep)
