"""
Find annotations that are probably wrong.

Every other quality check in this platform asks "is the model good?". This one
inverts the question: when a trained model is *confident* and disagrees with a
label, the label is a suspect. That turns a model you already have into a
proofreader for the data it was trained on.

Four findings, each with a different fix:

    wrong_class       a confident prediction of a different class, well placed
                      over a labelled box — the box is right, the label is not
    missing_label     a confident prediction where nothing is labelled — an
                      object someone forgot to draw
    spurious_label    a labelled box the model sees nothing in at all — often
                      a stray click, or a box left behind after a class rename
    loose_box         a confident, well-classified prediction that overlaps a
                      labelled box only loosely — the label's extent is off

A note on the method, because it decides how to read the output. Proper
label-error detection (cleanlab and friends) uses out-of-fold predictions, so
the model scoring an image never trained on it. This runs a model over data it
*was* trained on, which is the weaker setup — but it is weak in a specific,
safe direction. A model that memorised a bad label will agree with it, so
memorisation costs us findings we would otherwise make; it does not invent
findings that are not there. In other words: the flags are worth reviewing,
and a clean report is not proof the labels are clean.

Boxes are xyxy in absolute pixels, matching `detection_metrics`.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.services.detection_metrics import box_iou

logger = logging.getLogger(__name__)

FINDING_KINDS = (
    "wrong_class",
    "missing_label",
    "spurious_label",
    "loose_box",
)

# A finding is only worth a human's time if the model is sure. These are
# deliberately strict — the cost of a false flag is a reviewer losing trust in
# the whole report, which is worse than missing a few real errors.
DEFAULT_CONFIDENCE = 0.80

# Above this IoU, a prediction and a label are talking about the same object.
SAME_OBJECT_IOU = 0.5

# Between this and SAME_OBJECT_IOU, they overlap but disagree on extent.
LOOSE_BOX_IOU = 0.2

# Below this, a prediction is not about any labelled object at all.
UNRELATED_IOU = 0.1

# How severe each kind is, for ordering a review queue. A missing label and a
# wrong class both corrupt training signal directly; a loose box degrades it
# more gently.
_SEVERITY = {
    "wrong_class": 3,
    "missing_label": 3,
    "spurious_label": 2,
    "loose_box": 1,
}


def _as_xyxy(boxes: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(boxes, dtype=np.float32)
    if array.size == 0:
        return np.zeros((0, 4), dtype=np.float32)
    return array.reshape(-1, 4)


def audit_image(
    prediction: Dict[str, np.ndarray],
    target: Dict[str, np.ndarray],
    class_names: Optional[Dict[int, str]] = None,
    min_confidence: float = DEFAULT_CONFIDENCE,
) -> List[Dict[str, Any]]:
    """
    Compare one image's labels against a model's confident predictions.

    Returns a list of findings, each naming the kind, the boxes involved and
    the model's confidence. An empty list means nothing confident disagreed.
    """
    names = class_names or {}

    def name_of(label: int) -> str:
        return names.get(int(label), f"class_{int(label)}")

    pred_boxes = _as_xyxy(prediction.get("boxes", []))
    pred_scores = np.asarray(prediction.get("scores", []), dtype=np.float32).reshape(-1)
    pred_labels = np.asarray(prediction.get("labels", []), dtype=int).reshape(-1)

    gt_boxes = _as_xyxy(target.get("boxes", []))
    gt_labels = np.asarray(target.get("labels", []), dtype=int).reshape(-1)

    # Only confident predictions get to accuse a label of being wrong.
    keep = pred_scores >= min_confidence
    pred_boxes, pred_scores, pred_labels = (
        pred_boxes[keep], pred_scores[keep], pred_labels[keep]
    )

    findings: List[Dict[str, Any]] = []

    iou = (
        box_iou(pred_boxes, gt_boxes)
        if len(pred_boxes) and len(gt_boxes)
        else np.zeros((len(pred_boxes), len(gt_boxes)), dtype=np.float32)
    )

    # --- what the predictions say about the labels ------------------------
    for p in range(len(pred_boxes)):
        box = [round(float(v), 2) for v in pred_boxes[p]]
        confidence = round(float(pred_scores[p]), 4)

        if len(gt_boxes) == 0:
            findings.append({
                "kind": "missing_label",
                "confidence": confidence,
                "predicted_class": name_of(pred_labels[p]),
                "predicted_box": box,
                "note": "Confident detection on an image with no labels at all.",
            })
            continue

        best = int(np.argmax(iou[p]))
        best_iou = float(iou[p][best])

        if best_iou < UNRELATED_IOU:
            findings.append({
                "kind": "missing_label",
                "confidence": confidence,
                "predicted_class": name_of(pred_labels[p]),
                "predicted_box": box,
                "note": "Confident detection where nothing is labelled.",
            })
            continue

        same_class = int(gt_labels[best]) == int(pred_labels[p])

        if best_iou >= SAME_OBJECT_IOU and not same_class:
            findings.append({
                "kind": "wrong_class",
                "confidence": confidence,
                "predicted_class": name_of(pred_labels[p]),
                "labelled_class": name_of(gt_labels[best]),
                "predicted_box": box,
                "labelled_box": [round(float(v), 2) for v in gt_boxes[best]],
                "iou": round(best_iou, 4),
                "gt_index": best,
                "note": (
                    f"Model is {int(confidence * 100)}% sure this is a "
                    f"{name_of(pred_labels[p])}, but it is labelled "
                    f"{name_of(gt_labels[best])}."
                ),
            })
        elif LOOSE_BOX_IOU <= best_iou < SAME_OBJECT_IOU and same_class:
            findings.append({
                "kind": "loose_box",
                "confidence": confidence,
                "predicted_class": name_of(pred_labels[p]),
                "predicted_box": box,
                "labelled_box": [round(float(v), 2) for v in gt_boxes[best]],
                "iou": round(best_iou, 4),
                "gt_index": best,
                "note": (
                    "Same class, but the labelled box and the confident "
                    "prediction disagree on extent."
                ),
            })

    # --- labels nothing confident supports -------------------------------
    # Judged against *all* predictions rather than only confident ones: a
    # low-confidence detection on a box still means the model sees something
    # there, which is not a spurious label.
    all_boxes = _as_xyxy(prediction.get("boxes", []))
    all_iou = (
        box_iou(all_boxes, gt_boxes)
        if len(all_boxes) and len(gt_boxes)
        else np.zeros((len(all_boxes), len(gt_boxes)), dtype=np.float32)
    )

    for g in range(len(gt_boxes)):
        supported = (
            len(all_boxes) and float(all_iou[:, g].max()) >= UNRELATED_IOU
        )
        if not supported:
            findings.append({
                "kind": "spurious_label",
                # No prediction to be confident about; this finding is the
                # absence of one, so the model's certainty does not apply.
                "confidence": None,
                "labelled_class": name_of(gt_labels[g]),
                "labelled_box": [round(float(v), 2) for v in gt_boxes[g]],
                "gt_index": g,
                "note": "Nothing was detected here at any confidence.",
            })

    return findings


def rank_findings(findings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order a review queue: most damaging kind first, then most confident.

    A reviewer works top-down and stops when the findings stop being worth it,
    so the ordering is the feature.
    """
    return sorted(
        findings,
        key=lambda f: (
            -_SEVERITY.get(f.get("kind"), 0),
            -(f.get("confidence") or 0.0),
        ),
    )


def summarise(findings: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts by kind, plus the class pairs that get confused most."""
    by_kind = dict.fromkeys(FINDING_KINDS, 0)
    for finding in findings or []:
        kind = finding.get("kind")
        if kind in by_kind:
            by_kind[kind] += 1

    # Which labels are being mistaken for which — the actionable pattern in a
    # pile of wrong_class findings.
    pairs: Dict[Any, int] = {}
    for finding in findings or []:
        if finding.get("kind") != "wrong_class":
            continue
        key = (finding.get("labelled_class"), finding.get("predicted_class"))
        pairs[key] = pairs.get(key, 0) + 1

    confused = [
        {"labelled": labelled, "model_says": predicted, "count": count}
        for (labelled, predicted), count in pairs.items()
    ]
    confused.sort(key=lambda row: -row["count"])

    return {
        "total": len(findings or []),
        "by_kind": by_kind,
        "confused_pairs": confused[:10],
    }


def severity_of(kind: str) -> int:
    """How damaging a finding kind is. Exposed for callers that store it."""
    return _SEVERITY.get(kind, 0)
