"""
Per-image error analysis for detection models.

`detection_metrics` answers "how good is this model" with a number.
This module answers "where is it wrong, and wrong in what way" — which is the
question you actually act on. It classifies every prediction and every missed
ground-truth box into one of a handful of failure kinds, in the spirit of TIDE
(Bolya et al., 2020):

    background        nothing of interest is there — a hallucination
    wrong_class       found the object, named it wrong
    poor_localisation right class, box too loose or too tight to count
    duplicate         right class and well placed, but a higher-scoring
                      prediction already claimed that object
    missed            a ground-truth box no prediction covered

The distinction matters because the fixes differ. A pile of `wrong_class`
errors between two labels means those classes need disambiguating examples; a
pile of `poor_localisation` means the box regression is weak; `duplicate`
usually means NMS is too permissive; `background` on a cluttered dataset often
means more hard negatives are needed.

Boxes are xyxy in absolute pixels throughout, matching `detection_metrics`.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.services.detection_metrics import box_iou

logger = logging.getLogger(__name__)

# Below this IoU with any ground truth, a prediction is not a bad box — it is
# pointing at nothing. The split between "background" and "poor localisation"
# has to go somewhere, and 0.1 is TIDE's choice.
BACKGROUND_IOU = 0.1

_EPS = 1e-16

ERROR_KINDS = (
    "background",
    "wrong_class",
    "poor_localisation",
    "duplicate",
    "missed",
)


def _as_xyxy(boxes: Sequence[Sequence[float]]) -> np.ndarray:
    """Normalise a box list into an (N, 4) float array."""
    array = np.asarray(boxes, dtype=np.float32)
    if array.size == 0:
        return np.zeros((0, 4), dtype=np.float32)
    return array.reshape(-1, 4)


def gt_boxes_to_xyxy(boxes: Sequence[Dict[str, Any]]) -> Dict[str, np.ndarray]:
    """
    Convert stored annotation boxes into arrays the metrics code accepts.

    Annotations are persisted as {x, y, width, height} in absolute pixels with
    the origin at the box's top-left corner — the convention the VOC exporter
    writes straight through as xmin/ymin/xmax/ymax.
    """
    xyxy: List[List[float]] = []
    labels: List[int] = []
    for box in boxes or []:
        try:
            x = float(box.get("x", 0))
            y = float(box.get("y", 0))
            width = float(box.get("width", 0))
            height = float(box.get("height", 0))
        except (TypeError, ValueError):
            continue
        # A zero-area box contributes nothing and would make IoU undefined.
        if width <= 0 or height <= 0:
            continue
        xyxy.append([x, y, x + width, y + height])
        labels.append(int(box.get("class_id", 0)))

    return {
        "boxes": _as_xyxy(xyxy),
        "labels": np.asarray(labels, dtype=int),
    }


def version_boxes_to_annotations(
    boxes: Sequence[Dict[str, Any]], width: int, height: int
) -> List[Dict[str, Any]]:
    """
    Convert a version snapshot's boxes into the annotation shape.

    `dataset_version_images.boxes` stores YOLO's normalised centre format —
    ``{"class_id": int, "bbox_normalized": [cx, cy, w, h]}`` — because that is
    what the label .txt files beside the images contain. Live annotations are
    ``{x, y, width, height}`` in absolute pixels.

    Converting to the annotation shape rather than straight to arrays means the
    snapshot and the live table feed the identical downstream path, so there is
    one definition of how ground truth becomes metrics instead of two that can
    drift apart.
    """
    converted: List[Dict[str, Any]] = []
    for box in boxes or []:
        norm = box.get("bbox_normalized")
        if not norm or len(norm) < 4:
            continue
        try:
            cx, cy, bw, bh = (float(v) for v in norm[:4])
        except (TypeError, ValueError):
            continue
        pixel_width = bw * width
        pixel_height = bh * height
        if pixel_width <= 0 or pixel_height <= 0:
            continue
        converted.append({
            "x": (cx - bw / 2.0) * width,
            "y": (cy - bh / 2.0) * height,
            "width": pixel_width,
            "height": pixel_height,
            "class_id": int(box.get("class_id", 0)),
        })
    return converted


def detections_to_arrays(detections: Sequence[Dict[str, Any]]) -> Dict[str, np.ndarray]:
    """Convert inference output (`bbox` xyxy pixels) into metric arrays."""
    xyxy: List[List[float]] = []
    scores: List[float] = []
    labels: List[int] = []
    for detection in detections or []:
        bbox = detection.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        xyxy.append([float(v) for v in bbox[:4]])
        scores.append(float(detection.get("confidence", 0.0)))
        labels.append(int(detection.get("class_id", 0)))

    return {
        "boxes": _as_xyxy(xyxy),
        "scores": np.asarray(scores, dtype=np.float32),
        "labels": np.asarray(labels, dtype=int),
    }


def classify_image_errors(
    prediction: Dict[str, np.ndarray],
    target: Dict[str, np.ndarray],
    iou_threshold: float = 0.5,
    conf_threshold: float = 0.25,
    class_names: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """
    Classify one image's predictions and misses.

    Greedy matching by descending confidence, which is what every detection
    metric does and what makes `duplicate` a meaningful category: the first
    prediction to claim a ground-truth box wins it, and a later one covering
    the same object is a duplicate rather than a second true positive.

    Returns a dict with `true_positives`, `false_positives`, `false_negatives`
    and a `counts` summary.
    """
    names = class_names or {}

    pred_boxes = _as_xyxy(prediction.get("boxes", []))
    pred_scores = np.asarray(prediction.get("scores", []), dtype=np.float32).reshape(-1)
    pred_labels = np.asarray(prediction.get("labels", []), dtype=int).reshape(-1)

    gt_boxes = _as_xyxy(target.get("boxes", []))
    gt_labels = np.asarray(target.get("labels", []), dtype=int).reshape(-1)

    # Confidence filter first: everything below the operating point is simply
    # not a prediction the model is making at this threshold.
    keep = pred_scores >= conf_threshold
    pred_boxes, pred_scores, pred_labels = (
        pred_boxes[keep], pred_scores[keep], pred_labels[keep]
    )

    order = np.argsort(-pred_scores)
    pred_boxes, pred_scores, pred_labels = (
        pred_boxes[order], pred_scores[order], pred_labels[order]
    )

    # (n_pred, n_gt) IoU, empty-safe in both directions.
    iou = box_iou(pred_boxes, gt_boxes) if len(pred_boxes) and len(gt_boxes) else (
        np.zeros((len(pred_boxes), len(gt_boxes)), dtype=np.float32)
    )

    gt_claimed = np.zeros(len(gt_boxes), dtype=bool)

    true_positives: List[Dict[str, Any]] = []
    false_positives: List[Dict[str, Any]] = []

    def name_of(label: int) -> str:
        return names.get(int(label), f"class_{int(label)}")

    for p in range(len(pred_boxes)):
        entry = {
            "bbox": [round(float(v), 2) for v in pred_boxes[p]],
            "confidence": round(float(pred_scores[p]), 4),
            "class_id": int(pred_labels[p]),
            "class_name": name_of(pred_labels[p]),
        }

        if len(gt_boxes) == 0:
            false_positives.append({**entry, "kind": "background", "iou": 0.0})
            continue

        same_class = gt_labels == pred_labels[p]
        ious = iou[p]

        # Best same-class overlap decides TP / duplicate / poor localisation.
        same_class_ious = np.where(same_class, ious, -1.0)
        best_same = int(np.argmax(same_class_ious))
        best_same_iou = float(same_class_ious[best_same])

        if best_same_iou >= iou_threshold:
            if not gt_claimed[best_same]:
                gt_claimed[best_same] = True
                true_positives.append({
                    **entry,
                    "iou": round(best_same_iou, 4),
                    "gt_index": best_same,
                })
            else:
                # Correct in every way except that this object is already found.
                false_positives.append({
                    **entry,
                    "kind": "duplicate",
                    "iou": round(best_same_iou, 4),
                    "gt_index": best_same,
                })
            continue

        # Not a TP. Which kind of miss is it?
        best_any = int(np.argmax(ious))
        best_any_iou = float(ious[best_any])

        if best_any_iou < BACKGROUND_IOU:
            kind, reference = "background", None
        elif best_same_iou >= BACKGROUND_IOU:
            # Right class, overlapping the object, just not tightly enough.
            kind, reference = "poor_localisation", best_same
        else:
            # Overlaps something real, but that something is another class.
            kind, reference = "wrong_class", best_any

        record = {**entry, "kind": kind, "iou": round(max(best_any_iou, 0.0), 4)}
        if reference is not None:
            record["gt_index"] = reference
            record["gt_class_name"] = name_of(gt_labels[reference])
        false_positives.append(record)

    false_negatives = [
        {
            "bbox": [round(float(v), 2) for v in gt_boxes[g]],
            "class_id": int(gt_labels[g]),
            "class_name": name_of(gt_labels[g]),
            "kind": "missed",
            # The best any prediction managed on this object, which separates
            # "the model never saw it" from "it was close but below threshold".
            "best_iou": round(
                float(iou[:, g].max()) if len(pred_boxes) else 0.0, 4
            ),
        }
        for g in range(len(gt_boxes))
        if not gt_claimed[g]
    ]

    kind_counts = dict.fromkeys(ERROR_KINDS, 0)
    for record in false_positives:
        kind_counts[record["kind"]] = kind_counts.get(record["kind"], 0) + 1
    kind_counts["missed"] = len(false_negatives)

    tp, fp, fn = len(true_positives), len(false_positives), len(false_negatives)
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "counts": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "by_kind": kind_counts,
            # Per-image precision and recall, which is what makes a list of
            # images sortable by "worst first".
            "precision": round(tp / (tp + fp), 4) if (tp + fp) else 0.0,
            "recall": round(tp / (tp + fn), 4) if (tp + fn) else 0.0,
        },
    }


def confidence_sweep(
    predictions: Sequence[Dict[str, np.ndarray]],
    targets: Sequence[Dict[str, np.ndarray]],
    iou_threshold: float = 0.5,
    thresholds: Optional[Sequence[float]] = None,
) -> List[Dict[str, Any]]:
    """
    Precision, recall and F1 across confidence thresholds.

    This is the curve that answers the only deployment question that matters
    once a model trains: where do I set the confidence slider? A single mAP
    number cannot answer it, and the YOLO PR-curve PNG cannot be read off.

    Matching is done once at the lowest threshold and then re-counted, rather
    than re-matching per threshold: raising the confidence bar only ever
    removes predictions, so the greedy assignment of the survivors is
    unchanged. That makes this one pass over the data instead of twenty.
    """
    steps = list(thresholds) if thresholds else [round(0.05 * i, 2) for i in range(1, 20)]

    # Flattened TP flags and scores across the split, matched once.
    matched_flags: List[np.ndarray] = []
    matched_scores: List[np.ndarray] = []
    total_gt = 0

    for prediction, target in zip(predictions, targets):
        pred_boxes = _as_xyxy(prediction.get("boxes", []))
        pred_scores = np.asarray(prediction.get("scores", []), dtype=np.float32).reshape(-1)
        pred_labels = np.asarray(prediction.get("labels", []), dtype=int).reshape(-1)
        gt_boxes = _as_xyxy(target.get("boxes", []))
        gt_labels = np.asarray(target.get("labels", []), dtype=int).reshape(-1)

        total_gt += len(gt_boxes)

        if len(pred_boxes) == 0:
            continue

        order = np.argsort(-pred_scores)
        pred_boxes, pred_scores, pred_labels = (
            pred_boxes[order], pred_scores[order], pred_labels[order]
        )

        flags = np.zeros(len(pred_boxes), dtype=bool)
        if len(gt_boxes):
            iou = box_iou(pred_boxes, gt_boxes)
            claimed = np.zeros(len(gt_boxes), dtype=bool)
            for p in range(len(pred_boxes)):
                candidates = np.where(
                    (gt_labels == pred_labels[p]) & ~claimed, iou[p], -1.0
                )
                best = int(np.argmax(candidates))
                if float(candidates[best]) >= iou_threshold:
                    claimed[best] = True
                    flags[p] = True

        matched_flags.append(flags)
        matched_scores.append(pred_scores)

    if matched_flags:
        flags = np.concatenate(matched_flags)
        scores = np.concatenate(matched_scores)
    else:
        flags = np.zeros(0, dtype=bool)
        scores = np.zeros(0, dtype=np.float32)

    curve: List[Dict[str, Any]] = []
    for threshold in steps:
        kept = scores >= threshold
        tp = int(np.count_nonzero(flags & kept))
        fp = int(np.count_nonzero(~flags & kept))
        fn = int(total_gt - tp)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / total_gt if total_gt else 0.0
        f1 = 2 * precision * recall / max(precision + recall, _EPS)

        curve.append({
            "threshold": round(float(threshold), 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        })

    return curve


def best_operating_point(curve: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The threshold on a sweep with the highest F1."""
    if not curve:
        return None
    return max(curve, key=lambda point: point.get("f1", 0.0))


def compare_per_class(
    per_class_a: Sequence[Dict[str, Any]],
    per_class_b: Sequence[Dict[str, Any]],
    metric: str = "mAP50",
) -> List[Dict[str, Any]]:
    """
    Per-class deltas between two evaluations, worst regression first.

    The point of ordering by delta rather than by absolute score: a run that
    gains 6 mAP overall while losing 11 on one class is a regression someone
    needs to see, and an overall-mAP comparison hides it completely.

    Classes present in only one run are reported with the missing side as None
    rather than zero, so "newly added class" never reads as "scored zero".
    """
    by_name_a = {row.get("class_name"): row for row in per_class_a or []}
    by_name_b = {row.get("class_name"): row for row in per_class_b or []}

    rows: List[Dict[str, Any]] = []
    for name in sorted(set(by_name_a) | set(by_name_b)):
        a_row, b_row = by_name_a.get(name), by_name_b.get(name)
        a_value = float(a_row.get(metric, 0.0)) if a_row else None
        b_value = float(b_row.get(metric, 0.0)) if b_row else None

        rows.append({
            "class_name": name,
            "metric": metric,
            "a": round(a_value, 4) if a_value is not None else None,
            "b": round(b_value, 4) if b_value is not None else None,
            "delta": (
                round(b_value - a_value, 4)
                if a_value is not None and b_value is not None
                else None
            ),
            "status": (
                "added" if a_value is None
                else "removed" if b_value is None
                else "improved" if b_value > a_value
                else "regressed" if b_value < a_value
                else "unchanged"
            ),
        })

    # Regressions first (most negative delta), then classes only one run has.
    rows.sort(key=lambda row: (row["delta"] is None, row["delta"] or 0.0))
    return rows


def aggregate_error_kinds(per_image: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """Sum the error-kind histogram across a whole split."""
    totals = dict.fromkeys(ERROR_KINDS, 0)
    for image in per_image or []:
        by_kind = (image.get("counts") or {}).get("by_kind") or {}
        for kind, count in by_kind.items():
            totals[kind] = totals.get(kind, 0) + int(count)
    return totals


def class_confusion(
    per_image: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Which class pairs the model actually confuses, ranked.

    Built from the `wrong_class` false positives, so unlike a confusion matrix
    over a fixed grid this only reports pairs that genuinely collide — and each
    row names both sides in plain text instead of leaving the reader to index
    into an image.
    """
    pairs: Dict[Any, int] = {}
    for image in per_image or []:
        for record in image.get("false_positives") or []:
            if record.get("kind") != "wrong_class":
                continue
            key = (record.get("gt_class_name"), record.get("class_name"))
            if key[0] is None:
                continue
            pairs[key] = pairs.get(key, 0) + 1

    rows = [
        {"actual": actual, "predicted": predicted, "count": count}
        for (actual, predicted), count in pairs.items()
    ]
    rows.sort(key=lambda row: -row["count"])
    return rows


def _match_class_agnostic(
    pred_boxes: np.ndarray,
    pred_scores: np.ndarray,
    gt_boxes: np.ndarray,
    iou_threshold: float,
) -> Dict[str, np.ndarray]:
    """
    Pair predictions to ground truth ignoring labels, best score first.

    Returns `pred_to_gt` and `gt_to_pred` index maps, -1 where unpaired.

    Deliberately label-blind, unlike `classify_image_errors`: scoring must
    treat a wrong label as a miss, but the confusion matrix exists to say
    *which* label was used instead, and that is only knowable by pairing the
    boxes first and comparing the labels afterwards.
    """
    pred_to_gt = np.full(len(pred_boxes), -1, dtype=int)
    gt_to_pred = np.full(len(gt_boxes), -1, dtype=int)
    if len(pred_boxes) == 0 or len(gt_boxes) == 0:
        return {"pred_to_gt": pred_to_gt, "gt_to_pred": gt_to_pred}

    iou = box_iou(pred_boxes, gt_boxes)
    for p in np.argsort(-pred_scores):
        candidates = iou[p]
        # Highest overlap first, stopping at the threshold or the first free box.
        for g in np.argsort(-candidates):
            if float(candidates[g]) < iou_threshold:
                break
            if gt_to_pred[g] == -1:
                pred_to_gt[p] = int(g)
                gt_to_pred[g] = int(p)
                break
    return {"pred_to_gt": pred_to_gt, "gt_to_pred": gt_to_pred}


def confusion_matrix(
    predictions: Sequence[Dict[str, np.ndarray]],
    targets: Sequence[Dict[str, np.ndarray]],
    n_classes: int,
    iou_threshold: float = 0.5,
    conf_threshold: float = 0.25,
) -> Dict[str, Any]:
    """
    A full confusion matrix over the split, with a background row and column.

    `matrix[actual][predicted]`, where index `n_classes` means background: the
    last column counts ground truth nothing found, the last row counts
    predictions with no object behind them. A row reads as "what this class
    gets called"; a column as "what gets called this class".

    This complements `class_confusion`, which ranks only the pairs that
    actually collide and is the better thing to read first. The matrix is for
    when the question is the whole picture — including what was missed outright
    versus invented, which a pair list cannot show.

    Every ground-truth box and every prediction lands in exactly one cell, so
    rows sum to the ground truth per class and columns to the predictions. That
    is what the class-agnostic pairing buys: pairing by label instead would
    count a mislabelled object twice, once as a miss of its real class and
    again as an invention of the predicted one.
    """
    size = n_classes + 1
    background = n_classes
    matrix = [[0] * size for _ in range(size)]

    def slot(label: Any) -> int:
        try:
            value = int(label)
        except (TypeError, ValueError):
            return background
        return value if 0 <= value < n_classes else background

    for prediction, target in zip(predictions, targets):
        pred_boxes = _as_xyxy(prediction.get("boxes", []))
        pred_scores = np.asarray(prediction.get("scores", []), dtype=np.float32).reshape(-1)
        pred_labels = np.asarray(prediction.get("labels", []), dtype=int).reshape(-1)
        gt_boxes = _as_xyxy(target.get("boxes", []))
        gt_labels = np.asarray(target.get("labels", []), dtype=int).reshape(-1)

        # The matrix describes one operating point, so it sees only the
        # predictions the deployed model would surface.
        keep = pred_scores >= conf_threshold
        pred_boxes, pred_scores, pred_labels = (
            pred_boxes[keep], pred_scores[keep], pred_labels[keep]
        )

        paired = _match_class_agnostic(pred_boxes, pred_scores, gt_boxes, iou_threshold)
        pred_to_gt, gt_to_pred = paired["pred_to_gt"], paired["gt_to_pred"]

        for p in range(len(pred_boxes)):
            gt_index = int(pred_to_gt[p])
            row = slot(gt_labels[gt_index]) if gt_index >= 0 else background
            matrix[row][slot(pred_labels[p])] += 1

        for g in range(len(gt_boxes)):
            if gt_to_pred[g] < 0:
                matrix[slot(gt_labels[g])][background] += 1

    return {
        "matrix": matrix,
        "n_classes": n_classes,
        "background_index": background,
    }
