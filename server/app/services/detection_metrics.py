"""
COCO-style detection metrics (mAP50, mAP50-95, per-class AP/P/R).

Implemented directly on numpy so the RT-DETR and TorchVision backends can report
real validation numbers without pulling in pycocotools, which needs a C toolchain
on Windows.
"""
from typing import Dict, List, Sequence

import numpy as np

IOU_THRESHOLDS = np.linspace(0.5, 0.95, 10)

_EPS = 1e-16


def box_iou(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """IoU matrix between two sets of xyxy boxes. Returns shape [len(a), len(b)]."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)

    area_a = np.prod(np.clip(boxes_a[:, 2:] - boxes_a[:, :2], 0, None), axis=1)
    area_b = np.prod(np.clip(boxes_b[:, 2:] - boxes_b[:, :2], 0, None), axis=1)

    lt = np.maximum(boxes_a[:, None, :2], boxes_b[None, :, :2])
    rb = np.minimum(boxes_a[:, None, 2:], boxes_b[None, :, 2:])
    inter = np.prod(np.clip(rb - lt, 0, None), axis=2)

    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.maximum(union, _EPS), 0.0).astype(np.float32)


def _average_precision(recall: np.ndarray, precision: np.ndarray) -> float:
    """AP from a PR curve using COCO's 101-point interpolation."""
    if len(recall) == 0:
        return 0.0
    # Precision envelope: at each recall, the best precision achievable at or beyond it.
    envelope = np.maximum.accumulate(precision[::-1])[::-1]
    recall_points = np.linspace(0, 1, 101)
    idx = np.searchsorted(recall, recall_points, side="left")
    # Recall levels the curve never reaches contribute zero precision.
    interpolated = np.where(idx < len(envelope), envelope[np.clip(idx, 0, len(envelope) - 1)], 0.0)
    return float(interpolated.mean())


def _match_predictions(
    pred_boxes: np.ndarray,
    pred_labels: np.ndarray,
    gt_boxes: np.ndarray,
    gt_labels: np.ndarray,
) -> np.ndarray:
    """Match one image's predictions against its ground truth.

    Returns a bool array [n_pred, n_iou_thresholds] marking true positives.
    Each ground-truth box can satisfy at most one prediction per threshold.
    """
    correct = np.zeros((len(pred_boxes), len(IOU_THRESHOLDS)), dtype=bool)
    if len(pred_boxes) == 0 or len(gt_boxes) == 0:
        return correct

    iou = box_iou(gt_boxes, pred_boxes)
    # A prediction can only match ground truth of the same class.
    iou = iou * (gt_labels[:, None] == pred_labels[None, :])

    for t_idx, threshold in enumerate(IOU_THRESHOLDS):
        gt_idx, pred_idx = np.nonzero(iou >= threshold)
        if len(gt_idx) == 0:
            continue
        matches = np.stack((gt_idx, pred_idx), axis=1)
        if len(matches) > 1:
            # Highest IoU first, then keep one match per prediction and per GT box.
            matches = matches[iou[gt_idx, pred_idx].argsort()[::-1]]
            matches = matches[np.unique(matches[:, 1], return_index=True)[1]]
            matches = matches[np.unique(matches[:, 0], return_index=True)[1]]
        correct[matches[:, 1], t_idx] = True

    return correct


def evaluate_detections(
    predictions: Sequence[Dict[str, np.ndarray]],
    targets: Sequence[Dict[str, np.ndarray]],
    class_names: Dict[int, str],
) -> Dict:
    """Compute detection metrics over a full validation split.

    Args:
        predictions: Per image, a dict with 'boxes' (xyxy [N,4]), 'scores' [N], 'labels' [N].
        targets: Per image, a dict with 'boxes' (xyxy [M,4]) and 'labels' [M].
        class_names: Maps label id → display name. Ids must match those in the arrays.

    Returns:
        {"metrics": {"map50", "map50-95", "precision", "recall"}, "per_class_metrics": [...]}
    """
    all_correct: List[np.ndarray] = []
    all_scores: List[np.ndarray] = []
    all_pred_labels: List[np.ndarray] = []
    all_gt_labels: List[np.ndarray] = []

    for pred, target in zip(predictions, targets):
        pred_boxes = np.asarray(pred["boxes"], dtype=np.float32).reshape(-1, 4)
        pred_scores = np.asarray(pred["scores"], dtype=np.float32).reshape(-1)
        pred_labels = np.asarray(pred["labels"]).reshape(-1)
        gt_boxes = np.asarray(target["boxes"], dtype=np.float32).reshape(-1, 4)
        gt_labels = np.asarray(target["labels"]).reshape(-1)

        all_correct.append(_match_predictions(pred_boxes, pred_labels, gt_boxes, gt_labels))
        all_scores.append(pred_scores)
        all_pred_labels.append(pred_labels)
        all_gt_labels.append(gt_labels)

    empty = {
        "metrics": {"map50": 0.0, "map50-95": 0.0, "precision": 0.0, "recall": 0.0},
        "per_class_metrics": [],
    }
    if not all_correct:
        return empty

    correct = np.concatenate(all_correct) if all_correct else np.zeros((0, len(IOU_THRESHOLDS)), bool)
    scores = np.concatenate(all_scores) if all_scores else np.zeros(0, np.float32)
    pred_labels = np.concatenate(all_pred_labels) if all_pred_labels else np.zeros(0, int)
    gt_labels = np.concatenate(all_gt_labels) if all_gt_labels else np.zeros(0, int)

    if len(gt_labels) == 0:
        return empty

    order = np.argsort(-scores)
    correct, scores, pred_labels = correct[order], scores[order], pred_labels[order]

    present_classes, gt_counts = np.unique(gt_labels, return_counts=True)

    per_class_metrics = []
    ap_table = np.zeros((len(present_classes), len(IOU_THRESHOLDS)), dtype=np.float64)
    precisions = np.zeros(len(present_classes), dtype=np.float64)
    recalls = np.zeros(len(present_classes), dtype=np.float64)

    for c_idx, class_id in enumerate(present_classes):
        selected = pred_labels == class_id
        n_gt = gt_counts[c_idx]
        class_precision = 0.0
        class_recall = 0.0

        if selected.sum() > 0:
            tp = correct[selected].cumsum(axis=0)
            fp = (~correct[selected]).cumsum(axis=0)
            recall_curve = tp / (n_gt + _EPS)
            precision_curve = tp / np.maximum(tp + fp, _EPS)

            for t_idx in range(len(IOU_THRESHOLDS)):
                ap_table[c_idx, t_idx] = _average_precision(
                    recall_curve[:, t_idx], precision_curve[:, t_idx]
                )

            # Report P/R at the IoU 0.50 operating point with the best F1.
            p50, r50 = precision_curve[:, 0], recall_curve[:, 0]
            f1 = 2 * p50 * r50 / np.maximum(p50 + r50, _EPS)
            best = int(f1.argmax())
            class_precision = float(p50[best])
            class_recall = float(r50[best])

        precisions[c_idx] = class_precision
        recalls[c_idx] = class_recall
        per_class_metrics.append({
            "class_id": int(class_id),
            "class_name": class_names.get(int(class_id), f"class_{int(class_id)}"),
            "precision": class_precision,
            "recall": class_recall,
            "mAP50": float(ap_table[c_idx, 0]),
            "mAP50_95": float(ap_table[c_idx].mean()),
        })

    return {
        "metrics": {
            "map50": float(ap_table[:, 0].mean()),
            "map50-95": float(ap_table.mean()),
            "precision": float(precisions.mean()),
            "recall": float(recalls.mean()),
        },
        "per_class_metrics": per_class_metrics,
    }
