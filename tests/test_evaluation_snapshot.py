"""Tests for scoring against a frozen version snapshot.

Evaluation reads the live annotations table by default. Passing `version_id`
scores the version snapshot instead — what training actually consumed, after
preprocessing and augmentation, with the split already fixed.

The two sources store boxes differently: the live table keeps
{x, y, width, height} in absolute pixels, the snapshot keeps YOLO's normalised
centre format. These cover the conversion between them and the request
plumbing; the loader itself needs a database and is left to integration.
"""

import inspect

import numpy as np
import pytest

from app.api.v1.endpoints import evaluation as ev
from app.services.error_analysis import (
    gt_boxes_to_xyxy,
    version_boxes_to_annotations,
)

# ── Snapshot box conversion ──────────────────────────────────────────────────


def test_normalised_centre_box_becomes_a_pixel_annotation():
    # cx=0.5, cy=0.5, w=0.2, h=0.4 on a 100x200 image.
    annotations = version_boxes_to_annotations(
        [{"class_id": 1, "bbox_normalized": [0.5, 0.5, 0.2, 0.4]}], 100, 200
    )
    assert annotations == [
        {"x": 40.0, "y": 60.0, "width": 20.0, "height": 80.0, "class_id": 1}
    ]


def test_converted_boxes_feed_the_existing_ground_truth_path():
    """The whole point of converting to the annotation shape, not to arrays."""
    annotations = version_boxes_to_annotations(
        [{"class_id": 1, "bbox_normalized": [0.5, 0.5, 0.2, 0.4]}], 100, 200
    )
    target = gt_boxes_to_xyxy(annotations)
    assert target["boxes"].tolist() == [[40.0, 60.0, 60.0, 140.0]]
    assert target["labels"].tolist() == [1]


def test_a_full_frame_box_spans_the_whole_image():
    annotations = version_boxes_to_annotations(
        [{"class_id": 0, "bbox_normalized": [0.5, 0.5, 1.0, 1.0]}], 640, 480
    )
    assert annotations[0]["x"] == pytest.approx(0.0)
    assert annotations[0]["y"] == pytest.approx(0.0)
    assert annotations[0]["width"] == pytest.approx(640.0)
    assert annotations[0]["height"] == pytest.approx(480.0)


def test_class_id_defaults_to_zero_when_absent():
    annotations = version_boxes_to_annotations(
        [{"bbox_normalized": [0.5, 0.5, 0.2, 0.2]}], 100, 100
    )
    assert annotations[0]["class_id"] == 0


@pytest.mark.parametrize(
    "box",
    [
        {"class_id": 0},                                    # no geometry at all
        {"class_id": 0, "bbox_normalized": [0.5, 0.5]},     # truncated
        {"class_id": 0, "bbox_normalized": [0.5, 0.5, 0, 0.2]},    # zero width
        {"class_id": 0, "bbox_normalized": [0.5, 0.5, 0.2, 0]},    # zero height
        {"class_id": 0, "bbox_normalized": ["a", "b", "c", "d"]},  # unparseable
    ],
)
def test_unusable_snapshot_boxes_are_skipped(box):
    """A degenerate box would make IoU undefined rather than merely wrong."""
    assert version_boxes_to_annotations([box], 100, 100) == []


def test_empty_and_missing_box_lists_are_handled():
    assert version_boxes_to_annotations([], 100, 100) == []
    assert version_boxes_to_annotations(None, 100, 100) == []


def test_conversion_is_lossless_through_a_round_trip():
    """Pixel geometry recovered from normalised form matches what went in."""
    width, height = 800, 600
    x, y, w, h = 100.0, 150.0, 200.0, 120.0
    normalised = [
        (x + w / 2) / width,
        (y + h / 2) / height,
        w / width,
        h / height,
    ]
    back = version_boxes_to_annotations(
        [{"class_id": 3, "bbox_normalized": normalised}], width, height
    )[0]
    assert back["x"] == pytest.approx(x)
    assert back["y"] == pytest.approx(y)
    assert back["width"] == pytest.approx(w)
    assert back["height"] == pytest.approx(h)
    assert back["class_id"] == 3


def test_a_snapshot_box_and_a_live_box_of_the_same_object_agree():
    """Both sources must land on identical arrays, or runs are incomparable."""
    width, height = 200, 100
    live = [{"x": 20.0, "y": 10.0, "width": 60.0, "height": 40.0, "class_id": 2}]
    snapshot = version_boxes_to_annotations(
        [{"class_id": 2, "bbox_normalized": [50 / width, 30 / height, 60 / width, 40 / height]}],
        width,
        height,
    )
    assert np.allclose(gt_boxes_to_xyxy(live)["boxes"], gt_boxes_to_xyxy(snapshot)["boxes"])


# ── Request plumbing ─────────────────────────────────────────────────────────


def test_version_id_is_optional_and_defaults_to_the_live_dataset():
    assert ev.EvaluateRequest(job_id="j1").version_id is None


def test_version_id_is_accepted():
    assert ev.EvaluateRequest(job_id="j1", version_id="v1").version_id == "v1"


def test_both_ground_truth_sources_return_the_same_three_things():
    """Downstream scoring must not be able to tell which source it got."""
    source = inspect.getsource(ev._ground_truth_for)
    returns = [line.strip() for line in source.splitlines() if line.strip().startswith("return")]
    assert len(returns) == 2
    assert all(line.count(",") == 2 for line in returns), returns


def test_snapshot_loader_keeps_the_original_image_id():
    """Needed so a snapshot result can still deep-link into the annotator."""
    assert "source_image_id" in inspect.getsource(ev._snapshot_split)
    assert "original_image_id" in inspect.getsource(ev._snapshot_split)


def test_run_rejects_a_version_from_another_project():
    """A version id must not be a way into another project's snapshot."""
    source = inspect.getsource(ev.run_evaluation)
    assert "_version_dataset_id" in source
    assert "different project" in source
