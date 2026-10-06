"""
Polygon geometry for instance-segmentation versions.

The annotator stores three shapes in `annotations.boxes`: `box` (x/y/width/
height), `polygon` and `line` (a `points` list), and `joint` (a bare point).
A detection version only ever needed the first, so the version generator read
`box["width"]` for everything — which is absent on a polygon, came back 0, and
tripped the "skip degenerate box" guard. Polygon work was therefore dropped
silently on the way to training.

A segmentation version needs the opposite conversion: every instance expressed
as a polygon, because YOLO's segment format carries one `class x1 y1 x2 y2 …`
line per object and has no way to say "box only". A rectangle is a valid
polygon, so a `box` becomes its four corners rather than being discarded.

Everything here works in normalised [0, 1] coordinates and is pure, so the
conversion is testable without an image, a database or albumentations.
"""

import logging
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

Point = Tuple[float, float]

# Below this, a polygon has collapsed to a line or a dot and YOLO cannot build
# a mask from it. Matches the degenerate-box threshold the detection path uses.
MIN_EXTENT = 0.001

# Shapes that carry a `points` list rather than a width and height.
POINT_SHAPES = ("polygon", "line")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def box_corners(box: Dict, img_w: int, img_h: int) -> Optional[List[Point]]:
    """A `box` annotation as its four normalised corners, clockwise."""
    try:
        x = float(box.get("x", 0))
        y = float(box.get("y", 0))
        w = float(box.get("width", 0))
        h = float(box.get("height", 0))
    except (TypeError, ValueError):
        return None

    x_min, y_min = _clamp(x / img_w), _clamp(y / img_h)
    x_max, y_max = _clamp((x + w) / img_w), _clamp((y + h) / img_h)

    if (x_max - x_min) < MIN_EXTENT or (y_max - y_min) < MIN_EXTENT:
        return None

    return [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]


def instance_polygon(box: Dict, img_w: int, img_h: int) -> Optional[List[Point]]:
    """Normalised polygon for one annotation, or None if it cannot be one.

    A `joint` is a single point with no area, so it is not representable as a
    segmentation instance and is skipped — keypoint training would need a
    per-object skeleton the data model does not record.
    """
    if img_w <= 0 or img_h <= 0:
        return None

    shape = box.get("type", "box")

    if shape == "joint":
        return None

    if shape in POINT_SHAPES:
        raw = box.get("points") or []
        if len(raw) < 3:
            # A 2-point line has no interior; there is no mask to learn.
            return None
        points: List[Point] = []
        for p in raw:
            try:
                points.append(
                    (_clamp(float(p["x"]) / img_w), _clamp(float(p["y"]) / img_h))
                )
            except (TypeError, ValueError, KeyError):
                return None
        return points if _has_extent(points) else None

    return box_corners(box, img_w, img_h)


def _has_extent(points: Sequence[Point]) -> bool:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (max(xs) - min(xs)) >= MIN_EXTENT and (max(ys) - min(ys)) >= MIN_EXTENT


def polygon_bbox(points: Sequence[Point]) -> Tuple[float, float, float, float]:
    """The polygon's axis-aligned bounds as normalised (x_min, y_min, w, h).

    Preflight's structural stage and the evaluation workbench both read boxes,
    not masks, so a segmentation version still records a box per instance —
    derived from the polygon rather than stored alongside it, so the two can
    never disagree.
    """
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    x_min, y_min = min(xs), min(ys)
    return x_min, y_min, max(xs) - x_min, max(ys) - y_min


def format_segment_line(class_id: int, points: Sequence[Point]) -> str:
    """One YOLO segmentation label line: `class x1 y1 x2 y2 …`, normalised."""
    coords = " ".join(f"{_clamp(x):.6f} {_clamp(y):.6f}" for x, y in points)
    return f"{int(class_id)} {coords}"


def count_polygon_instances(annotations: Sequence[Dict]) -> int:
    """How many stored instances could become a segmentation mask.

    Drives both the "this dataset has no polygons" guard on generating a
    segment version and the hint the UI shows next to the task choice.
    """
    total = 0
    for annotation in annotations:
        for box in annotation.get("boxes") or []:
            if box.get("type") in POINT_SHAPES and len(box.get("points") or []) >= 3:
                total += 1
    return total
