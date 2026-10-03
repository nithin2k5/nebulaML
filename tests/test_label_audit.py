"""Unit tests for label-error detection.

The behaviour that matters is restraint: a finding costs a reviewer's
attention, so an unconfident model must not accuse anyone, and a label the
model merely scores low must not be called spurious. These tests pin each
finding kind and each case where the audit should stay quiet.
"""

import numpy as np
import pytest
from app.services import label_audit as la

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


def _kinds(findings):
    return sorted(f["kind"] for f in findings)


# ---------------------------------------------------------------------------
# Agreement produces nothing
# ---------------------------------------------------------------------------

def test_a_label_the_model_agrees_with_is_not_flagged():
    findings = la.audit_image(
        _pred([[0, 0, 10, 10]], [0.95], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        CLASS_NAMES,
    )
    assert findings == []


def test_an_empty_image_with_no_labels_is_not_flagged():
    assert la.audit_image(_pred([], [], []), _gt([], []), CLASS_NAMES) == []


# ---------------------------------------------------------------------------
# wrong_class
# ---------------------------------------------------------------------------

def test_a_confident_disagreement_on_class_is_flagged():
    findings = la.audit_image(
        _pred([[0, 0, 10, 10]], [0.93], [1]),   # model says truck
        _gt([[0, 0, 10, 10]], [0]),             # labelled car
        CLASS_NAMES,
    )
    assert _kinds(findings) == ["wrong_class"]
    finding = findings[0]
    assert finding["labelled_class"] == "car"
    assert finding["predicted_class"] == "truck"
    # The note has to name both sides — a reviewer reads it without the boxes.
    assert "car" in finding["note"] and "truck" in finding["note"]


def test_an_unconfident_disagreement_is_not_flagged():
    """A hesitant model is not evidence against a human label."""
    findings = la.audit_image(
        _pred([[0, 0, 10, 10]], [0.35], [1]),
        _gt([[0, 0, 10, 10]], [0]),
        CLASS_NAMES,
    )
    assert findings == []


def test_the_confidence_floor_is_configurable():
    args = (_pred([[0, 0, 10, 10]], [0.6], [1]), _gt([[0, 0, 10, 10]], [0]), CLASS_NAMES)
    assert la.audit_image(*args) == []
    assert _kinds(la.audit_image(*args, min_confidence=0.5)) == ["wrong_class"]


# ---------------------------------------------------------------------------
# missing_label
# ---------------------------------------------------------------------------

def test_a_confident_detection_with_nothing_labelled_nearby_is_a_missing_label():
    findings = la.audit_image(
        _pred([[100, 100, 150, 150]], [0.91], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        CLASS_NAMES,
    )
    assert "missing_label" in _kinds(findings)


def test_a_confident_detection_on_a_wholly_unlabelled_image_is_a_missing_label():
    findings = la.audit_image(
        _pred([[0, 0, 10, 10]], [0.97], [0]),
        _gt([], []),
        CLASS_NAMES,
    )
    assert _kinds(findings) == ["missing_label"]
    assert findings[0]["predicted_class"] == "car"


# ---------------------------------------------------------------------------
# spurious_label
# ---------------------------------------------------------------------------

def test_a_label_with_no_detection_at_all_is_spurious():
    findings = la.audit_image(
        _pred([], [], []),
        _gt([[0, 0, 10, 10]], [0]),
        CLASS_NAMES,
    )
    assert _kinds(findings) == ["spurious_label"]
    assert findings[0]["labelled_class"] == "car"
    # There is no prediction here, so there is no confidence to report.
    assert findings[0]["confidence"] is None


def test_a_label_the_model_sees_weakly_is_not_spurious():
    """Judged against all predictions, not just confident ones — a low-score
    detection still means something is there."""
    findings = la.audit_image(
        _pred([[0, 0, 10, 10]], [0.05], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        CLASS_NAMES,
    )
    assert "spurious_label" not in _kinds(findings)


# ---------------------------------------------------------------------------
# loose_box
# ---------------------------------------------------------------------------

def test_a_partially_overlapping_confident_box_of_the_same_class_is_a_loose_box():
    """IoU 1/3: same object, disputed extent."""
    findings = la.audit_image(
        _pred([[0, 0, 30, 10]], [0.9], [0]),
        _gt([[0, 0, 10, 10]], [0]),
        CLASS_NAMES,
    )
    assert _kinds(findings) == ["loose_box"]
    assert findings[0]["iou"] == pytest.approx(1 / 3, abs=1e-3)


def test_a_tiny_overlap_is_a_missing_label_not_a_loose_box():
    """Below the unrelated-IoU floor the prediction is about a different
    object, so the reading is a missing label."""
    findings = la.audit_image(
        _pred([[95, 0, 195, 10]], [0.9], [0]),
        _gt([[0, 0, 100, 10]], [0]),
        CLASS_NAMES,
    )
    assert "missing_label" in _kinds(findings)
    assert "loose_box" not in _kinds(findings)


# ---------------------------------------------------------------------------
# Ranking and summary
# ---------------------------------------------------------------------------

def test_ranking_puts_damaging_kinds_first_then_the_most_confident():
    ranked = la.rank_findings([
        {"kind": "loose_box", "confidence": 0.99},
        {"kind": "wrong_class", "confidence": 0.85},
        {"kind": "spurious_label", "confidence": None},
        {"kind": "missing_label", "confidence": 0.95},
    ])
    assert [f["kind"] for f in ranked] == [
        "missing_label",   # severity 3, confidence .95
        "wrong_class",     # severity 3, confidence .85
        "spurious_label",  # severity 2
        "loose_box",       # severity 1
    ]


def test_ranking_tolerates_a_missing_confidence():
    """spurious_label carries no confidence, so the sort key must not blow up."""
    ranked = la.rank_findings([{"kind": "spurious_label", "confidence": None}])
    assert len(ranked) == 1


def test_summary_counts_every_kind_even_at_zero():
    summary = la.summarise([
        {"kind": "wrong_class", "labelled_class": "car", "predicted_class": "truck"},
        {"kind": "wrong_class", "labelled_class": "car", "predicted_class": "truck"},
        {"kind": "missing_label"},
    ])
    assert summary["total"] == 3
    assert summary["by_kind"]["wrong_class"] == 2
    assert summary["by_kind"]["missing_label"] == 1
    # A zero is information: it says that kind was checked and not found.
    assert summary["by_kind"]["loose_box"] == 0


def test_summary_surfaces_the_confused_label_pairs():
    """The actionable pattern in a pile of wrong_class findings."""
    summary = la.summarise([
        {"kind": "wrong_class", "labelled_class": "car", "predicted_class": "truck"},
        {"kind": "wrong_class", "labelled_class": "car", "predicted_class": "truck"},
        {"kind": "wrong_class", "labelled_class": "truck", "predicted_class": "car"},
        {"kind": "missing_label"},
    ])
    assert summary["confused_pairs"][0] == {
        "labelled": "car", "model_says": "truck", "count": 2
    }
    assert len(summary["confused_pairs"]) == 2


def test_summary_of_nothing_is_all_zeroes():
    summary = la.summarise([])
    assert summary["total"] == 0
    assert set(summary["by_kind"]) == set(la.FINDING_KINDS)
    assert summary["confused_pairs"] == []


def test_every_finding_kind_has_a_severity():
    """rank_findings falls back to 0, which would silently sink a new kind."""
    for kind in la.FINDING_KINDS:
        assert la.severity_of(kind) > 0
