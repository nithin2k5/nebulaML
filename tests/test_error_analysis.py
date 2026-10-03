"""Unit tests for per-image detection error analysis.

The interesting behaviour is the classification boundary: the same prediction
is a true positive, a duplicate, a localisation error or a hallucination
depending on IoU, class and what another prediction already claimed. These
tests pin each of those cases with hand-built boxes.

Boxes are xyxy in absolute pixels, matching detection_metrics.
"""

import numpy as np
import pytest
from app.services import error_analysis as ea

CLASS_NAMES = {0: "car", 1: "truck"}


def _pred(boxes, scores, labels):
    return {
        "boxes": np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
        "scores": np.asarray(scores, dtype=np.float32),
        "labels": np.asarray(labels, dtype=int),
    }


def _gt(boxes, labels):
    return {
        "boxes": np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
        "labels": np.asarray(labels, dtype=int),
    }


# ---------------------------------------------------------------------------
# Format conversion
# ---------------------------------------------------------------------------

def test_stored_annotations_convert_from_xywh_to_xyxy():
    """Annotations are {x, y, width, height} top-left in absolute pixels."""
    converted = ea.gt_boxes_to_xyxy([
        {"x": 10, "y": 20, "width": 30, "height": 40, "class_id": 1},
    ])
    np.testing.assert_allclose(converted["boxes"][0], [10, 20, 40, 60])
    assert converted["labels"].tolist() == [1]


def test_zero_area_annotations_are_dropped():
    """A degenerate box makes IoU undefined, so it must not reach the matcher."""
    converted = ea.gt_boxes_to_xyxy([
        {"x": 10, "y": 10, "width": 0, "height": 40, "class_id": 0},
        {"x": 10, "y": 10, "width": 5, "height": 5, "class_id": 0},
    ])
    assert len(converted["boxes"]) == 1


def test_malformed_annotations_are_skipped_not_fatal():
    converted = ea.gt_boxes_to_xyxy([
        {"x": "oops", "y": 1, "width": 2, "height": 3},
        {"x": 0, "y": 0, "width": 4, "height": 4, "class_id": 0},
    ])
    assert len(converted["boxes"]) == 1


def test_detections_convert_from_inference_output():
    converted = ea.detections_to_arrays([
        {"bbox": [1, 2, 3, 4], "confidence": 0.9, "class_id": 1},
        {"bbox": None, "confidence": 0.5, "class_id": 0},  # dropped
    ])
    assert len(converted["boxes"]) == 1
    assert converted["scores"].tolist() == [pytest.approx(0.9)]
    assert converted["labels"].tolist() == [1]


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def test_a_well_placed_prediction_is_a_true_positive():
    result = ea.classify_image_errors(
        _pred([[0, 0, 10, 10]], [0.9], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["tp"] == 1
    assert result["counts"]["fp"] == 0
    assert result["counts"]["fn"] == 0
    assert result["true_positives"][0]["iou"] == pytest.approx(1.0)


def test_a_prediction_on_empty_background_is_a_hallucination():
    result = ea.classify_image_errors(
        _pred([[0, 0, 10, 10]], [0.9], [0]),
        _gt([], []),
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["by_kind"]["background"] == 1
    assert result["counts"]["fp"] == 1


def test_a_prediction_far_from_any_object_is_background_not_localisation():
    result = ea.classify_image_errors(
        _pred([[500, 500, 510, 510]], [0.9], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["by_kind"]["background"] == 1
    assert result["counts"]["by_kind"]["poor_localisation"] == 0
    assert result["counts"]["fn"] == 1  # the real object was still missed


def test_right_class_but_a_loose_box_is_a_localisation_error():
    """A 30x10 box over a 10x10 object: IoU 1/3 — overlapping enough to be the
    same object, too loose to count as a hit."""
    result = ea.classify_image_errors(
        _pred([[0, 0, 30, 10]], [0.9], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        iou_threshold=0.5,
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["by_kind"]["poor_localisation"] == 1
    assert result["counts"]["tp"] == 0


def test_iou_exactly_at_the_threshold_counts_as_a_hit():
    """A 20x10 box over a 10x10 object is IoU 0.5 exactly; the comparison is
    inclusive, matching detection_metrics."""
    result = ea.classify_image_errors(
        _pred([[0, 0, 20, 10]], [0.9], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        iou_threshold=0.5,
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["tp"] == 1


def test_a_well_placed_box_with_the_wrong_label_is_a_class_error():
    result = ea.classify_image_errors(
        _pred([[0, 0, 10, 10]], [0.9], [1]),
        _gt([[0, 0, 10, 10]], [0]),
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["by_kind"]["wrong_class"] == 1
    error = result["false_positives"][0]
    # Both sides are named, so the UI never has to resolve ids itself.
    assert error["class_name"] == "truck"
    assert error["gt_class_name"] == "car"


def test_a_second_prediction_on_a_claimed_object_is_a_duplicate():
    """The higher-scoring box wins the object; the other is not a second TP."""
    result = ea.classify_image_errors(
        _pred([[0, 0, 10, 10], [0, 0, 10, 10]], [0.9, 0.8], [0, 0]),
        _gt([[0, 0, 10, 10]], [0]),
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["tp"] == 1
    assert result["counts"]["by_kind"]["duplicate"] == 1


def test_the_highest_scoring_prediction_wins_the_object():
    """Matching is greedy by confidence, not by input order."""
    result = ea.classify_image_errors(
        # The lower-confidence box is listed first on purpose.
        _pred([[0, 0, 10, 10], [0, 0, 10, 10]], [0.4, 0.95], [0, 0]),
        _gt([[0, 0, 10, 10]], [0]),
        class_names=CLASS_NAMES,
    )
    assert result["true_positives"][0]["confidence"] == pytest.approx(0.95)


def test_an_unmatched_object_is_a_miss_and_records_its_best_overlap():
    """`best_iou` separates "never saw it" from "nearly had it"."""
    result = ea.classify_image_errors(
        _pred([[0, 0, 20, 10]], [0.9], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        iou_threshold=0.9,
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["fn"] == 1
    miss = result["false_negatives"][0]
    assert miss["kind"] == "missed"
    assert miss["best_iou"] == pytest.approx(0.5)


def test_predictions_below_the_confidence_threshold_are_ignored():
    result = ea.classify_image_errors(
        _pred([[0, 0, 10, 10]], [0.1], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        conf_threshold=0.5,
        class_names=CLASS_NAMES,
    )
    # Not counted as a prediction at all, so the object reads as missed.
    assert result["counts"]["tp"] == 0
    assert result["counts"]["fp"] == 0
    assert result["counts"]["fn"] == 1


def test_an_empty_prediction_set_on_an_empty_image_is_clean():
    result = ea.classify_image_errors(_pred([], [], []), _gt([], []))
    assert result["counts"] == {
        "tp": 0, "fp": 0, "fn": 0,
        "by_kind": {kind: 0 for kind in ea.ERROR_KINDS},
        "precision": 0.0, "recall": 0.0,
    }


def test_per_image_precision_and_recall():
    result = ea.classify_image_errors(
        # One hit, one hallucination; two objects, so one is missed.
        _pred([[0, 0, 10, 10], [100, 100, 110, 110]], [0.9, 0.8], [0, 0]),
        _gt([[0, 0, 10, 10], [50, 50, 60, 60]], [0, 0]),
        class_names=CLASS_NAMES,
    )
    assert result["counts"]["precision"] == pytest.approx(0.5)
    assert result["counts"]["recall"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Confidence sweep
# ---------------------------------------------------------------------------

def test_sweep_trades_recall_for_precision_as_the_threshold_rises():
    predictions = [
        _pred([[0, 0, 10, 10], [100, 100, 110, 110]], [0.9, 0.3], [0, 0]),
    ]
    targets = [_gt([[0, 0, 10, 10]], [0])]

    curve = ea.confidence_sweep(predictions, targets, thresholds=[0.2, 0.5])
    low, high = curve[0], curve[1]

    # At 0.2 the spurious box counts against precision; at 0.5 it is gone.
    assert low["fp"] == 1
    assert high["fp"] == 0
    assert high["precision"] > low["precision"]
    # Recall is unaffected, because the dropped box was never a hit.
    assert low["recall"] == high["recall"] == pytest.approx(1.0)


def test_sweep_counts_misses_against_total_ground_truth():
    """Raising the bar past every prediction must leave recall at zero, and
    `fn` equal to the number of objects — not to zero."""
    predictions = [_pred([[0, 0, 10, 10]], [0.4], [0])]
    targets = [_gt([[0, 0, 10, 10]], [0])]

    curve = ea.confidence_sweep(predictions, targets, thresholds=[0.9])
    assert curve[0] == {
        "threshold": 0.9, "tp": 0, "fp": 0, "fn": 1,
        "precision": 0.0, "recall": 0.0, "f1": 0.0,
    }


def test_sweep_does_not_double_count_one_object():
    """Two predictions on one object: one TP and one FP, at every threshold."""
    predictions = [_pred([[0, 0, 10, 10], [0, 0, 10, 10]], [0.9, 0.8], [0, 0])]
    targets = [_gt([[0, 0, 10, 10]], [0])]

    curve = ea.confidence_sweep(predictions, targets, thresholds=[0.5])
    assert curve[0]["tp"] == 1
    assert curve[0]["fp"] == 1


def test_sweep_over_an_image_with_no_predictions():
    curve = ea.confidence_sweep([_pred([], [], [])], [_gt([[0, 0, 5, 5]], [0])],
                                thresholds=[0.5])
    assert curve[0]["fn"] == 1
    assert curve[0]["recall"] == 0.0


def test_best_operating_point_maximises_f1():
    curve = [
        {"threshold": 0.1, "f1": 0.4},
        {"threshold": 0.5, "f1": 0.8},
        {"threshold": 0.9, "f1": 0.2},
    ]
    assert ea.best_operating_point(curve)["threshold"] == 0.5
    assert ea.best_operating_point([]) is None


# ---------------------------------------------------------------------------
# Run comparison
# ---------------------------------------------------------------------------

def test_comparison_puts_the_worst_regression_first():
    """The headline case: overall mAP rises while one class collapses."""
    run_a = [
        {"class_name": "car", "mAP50": 0.60},
        {"class_name": "bicycle", "mAP50": 0.70},
    ]
    run_b = [
        {"class_name": "car", "mAP50": 0.66},
        {"class_name": "bicycle", "mAP50": 0.59},
    ]

    rows = ea.compare_per_class(run_a, run_b)

    assert rows[0]["class_name"] == "bicycle"
    assert rows[0]["delta"] == pytest.approx(-0.11)
    assert rows[0]["status"] == "regressed"
    assert rows[1]["status"] == "improved"


def test_a_class_only_one_run_has_is_not_reported_as_zero():
    rows = ea.compare_per_class(
        [{"class_name": "car", "mAP50": 0.5}],
        [{"class_name": "car", "mAP50": 0.5}, {"class_name": "van", "mAP50": 0.3}],
    )
    van = next(row for row in rows if row["class_name"] == "van")
    assert van["a"] is None
    assert van["delta"] is None
    assert van["status"] == "added"


def test_comparison_can_use_another_metric():
    rows = ea.compare_per_class(
        [{"class_name": "car", "recall": 0.4}],
        [{"class_name": "car", "recall": 0.9}],
        metric="recall",
    )
    assert rows[0]["delta"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_error_kinds_aggregate_across_images():
    per_image = [
        {"counts": {"by_kind": {"background": 2, "missed": 1}}},
        {"counts": {"by_kind": {"background": 1, "duplicate": 3}}},
    ]
    totals = ea.aggregate_error_kinds(per_image)
    assert totals["background"] == 3
    assert totals["duplicate"] == 3
    assert totals["missed"] == 1
    assert totals["wrong_class"] == 0


def test_class_confusion_ranks_the_pairs_that_actually_collide():
    per_image = [
        {"false_positives": [
            {"kind": "wrong_class", "class_name": "truck", "gt_class_name": "car"},
            {"kind": "wrong_class", "class_name": "truck", "gt_class_name": "car"},
            {"kind": "background", "class_name": "car"},
        ]},
        {"false_positives": [
            {"kind": "wrong_class", "class_name": "car", "gt_class_name": "truck"},
        ]},
    ]
    rows = ea.class_confusion(per_image)

    assert rows[0] == {"actual": "car", "predicted": "truck", "count": 2}
    assert rows[1] == {"actual": "truck", "predicted": "car", "count": 1}
    # A background FP has no counterpart class, so it is not a confusion.
    assert len(rows) == 2
