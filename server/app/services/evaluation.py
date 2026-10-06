"""
Model evaluation: score a finished model against a dataset version's split.

Training jobs already report validation metrics, but each backend computes them
its own way, so two runs were never comparable. An evaluation run re-scores a
*finished* model through one metric path — `detection_metrics.evaluate_detections`,
the same code the RT-DETR and TorchVision trainers use — so a YOLO run and an
RT-DETR run can be put side by side.

Two numbers with different meanings come out of a run, and the distinction
matters for reading the results:

* **mAP** is threshold-free. It is computed from predictions down to
  `METRIC_SCORE_FLOOR` so the precision/recall curve is complete; filtering to
  the user's confidence first would truncate the curve and understate AP.
* **Precision / recall / the error breakdown** are properties of one operating
  point, so they are computed at the run's `conf_threshold`.

Per-box rows are persisted only for predictions at or above `conf_threshold`.
The floor exists to make the curve honest, not to fill the table with 0.002
confidence noise.
"""
import json
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.core.logging import logger
from app.db.session import get_db_connection
from app.services.detection_metrics import box_iou, evaluate_detections

# Inference floor for the metric pass. Low enough to complete the PR curve,
# high enough that a 2000-image split does not return a million boxes.
METRIC_SCORE_FLOOR = 0.001

# A prediction overlapping a same-class box by at least this much is treated as
# an attempt at that object — a localisation miss — rather than an invention.
LOCALIZATION_IOU_FLOOR = 0.1

# Confidence levels reported in the threshold sweep.
SWEEP_THRESHOLDS: Tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(1, 20))

# How many images to push through the model at once.
_BATCH_SIZE = 16

# NMS overlap used while decoding predictions. Distinct from the matching
# IoU a run is configured with — see the comment at its use site.
_NMS_IOU = 0.45

# How many per-box rows to send per executemany.
_INSERT_CHUNK = 500

_EPS = 1e-16


# ── Ground truth ─────────────────────────────────────────────────────────────


def gt_to_xyxy(boxes: Sequence[Dict], width: int, height: int) -> Tuple[np.ndarray, np.ndarray]:
    """Convert a `dataset_version_images.boxes` payload to absolute xyxy.

    Versioning stores each box as ``{"class_id": int, "bbox_normalized":
    [cx, cy, w, h]}`` — YOLO's normalised centre format. Predictions arrive in
    absolute xyxy, so ground truth is converted to match rather than the other
    way round, which keeps IoU in pixel space where the thresholds mean what
    people expect.
    """
    xyxy: List[List[float]] = []
    labels: List[int] = []
    for box in boxes or []:
        norm = box.get("bbox_normalized")
        if not norm or len(norm) < 4:
            continue
        cx, cy, bw, bh = (float(v) for v in norm[:4])
        xyxy.append([
            (cx - bw / 2.0) * width,
            (cy - bh / 2.0) * height,
            (cx + bw / 2.0) * width,
            (cy + bh / 2.0) * height,
        ])
        labels.append(int(box.get("class_id", 0)))

    if not xyxy:
        return np.zeros((0, 4), dtype=np.float32), np.zeros(0, dtype=int)
    return np.asarray(xyxy, dtype=np.float32), np.asarray(labels, dtype=int)


def predictions_to_arrays(
    detections: Sequence[Dict], class_index: Dict[str, int]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert inference output to (boxes xyxy, scores, labels).

    Labels are resolved by *name* against the version's class list, not by the
    model's own class ids. A model trained elsewhere — a stock COCO checkpoint,
    say — numbers its classes differently, and trusting its ids would silently
    score 'person' against whatever happens to sit at index 0 here. A name that
    the version does not define resolves to -1, which can only ever be a false
    positive.
    """
    boxes: List[List[float]] = []
    scores: List[float] = []
    labels: List[int] = []
    for det in detections or []:
        bbox = det.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        boxes.append([float(v) for v in bbox[:4]])
        scores.append(float(det.get("confidence", 0.0)))
        name = det.get("class_name")
        if name in class_index:
            labels.append(class_index[name])
        else:
            labels.append(-1)

    if not boxes:
        return (
            np.zeros((0, 4), dtype=np.float32),
            np.zeros(0, dtype=np.float32),
            np.zeros(0, dtype=int),
        )
    return (
        np.asarray(boxes, dtype=np.float32),
        np.asarray(scores, dtype=np.float32),
        np.asarray(labels, dtype=int),
    )


# ── Matching ─────────────────────────────────────────────────────────────────


def greedy_match(
    pred_boxes: np.ndarray,
    pred_scores: np.ndarray,
    pred_labels: np.ndarray,
    gt_boxes: np.ndarray,
    gt_labels: np.ndarray,
    iou_threshold: float,
    class_agnostic: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Match predictions to ground truth at one IoU threshold, best score first.

    Returns ``(pred_to_gt, gt_to_pred, pred_iou)``: for each prediction the
    index of the ground-truth box it claimed (or -1), the inverse map, and the
    IoU of the claim (0.0 when unmatched).

    Confidence order is what makes this deterministic and fair: the model's
    best guess gets first refusal on each object, so a lower-scoring duplicate
    cannot steal the match and turn a correct detection into an error.

    With ``class_agnostic``, a prediction may claim a box of any class. Scoring
    needs the class-aware pass (a wrong label is a miss), but the confusion
    matrix needs this one — it is what lets a box be reported as "this class,
    called that class" instead of as an unrelated miss and invention.
    """
    n_pred, n_gt = len(pred_boxes), len(gt_boxes)
    pred_to_gt = np.full(n_pred, -1, dtype=int)
    gt_to_pred = np.full(n_gt, -1, dtype=int)
    pred_iou = np.zeros(n_pred, dtype=np.float32)
    if n_pred == 0 or n_gt == 0:
        return pred_to_gt, gt_to_pred, pred_iou

    iou = box_iou(pred_boxes, gt_boxes)
    if class_agnostic:
        eligible = iou
    else:
        # Only a same-class box can be claimed; everything else is masked out.
        eligible = iou * (pred_labels[:, None] == gt_labels[None, :])

    for pred_idx in np.argsort(-pred_scores):
        candidates = eligible[pred_idx]
        best_gt = -1
        best_iou = 0.0
        for gt_idx in np.argsort(-candidates):
            score = float(candidates[gt_idx])
            if score < iou_threshold:
                break
            if gt_to_pred[gt_idx] == -1:
                best_gt, best_iou = int(gt_idx), score
                break
        if best_gt >= 0:
            pred_to_gt[pred_idx] = best_gt
            gt_to_pred[best_gt] = int(pred_idx)
            pred_iou[pred_idx] = best_iou

    return pred_to_gt, gt_to_pred, pred_iou


def count_outcomes(
    pred_boxes: np.ndarray,
    pred_scores: np.ndarray,
    pred_labels: np.ndarray,
    gt_boxes: np.ndarray,
    gt_labels: np.ndarray,
    iou_threshold: float,
) -> Tuple[int, int, int]:
    """(tp, fp, fn) for one image at one IoU threshold."""
    pred_to_gt, gt_to_pred, _ = greedy_match(
        pred_boxes, pred_scores, pred_labels, gt_boxes, gt_labels, iou_threshold
    )
    tp = int((pred_to_gt >= 0).sum())
    return tp, len(pred_boxes) - tp, int((gt_to_pred < 0).sum())


def _diagnose_false_positive(
    iou_row: Optional[np.ndarray],
    class_id: int,
    gt_labels: np.ndarray,
    iou_threshold: float,
) -> Tuple[str, int, float]:
    """Say what kind of mistake one unmatched prediction is.

    Returns ``(error_type, blamed_gt_index, iou)``, where the blamed index is
    the ground-truth box the mistake is about, or -1 when there is none.

    Order of the checks is the diagnosis. A box that already overlaps a
    same-class object is a duplicate; failing that, overlapping the right class
    loosely is a localisation problem; failing that, overlapping the wrong
    class tightly is a labelling problem; what is left was invented.
    """
    if iou_row is None or len(gt_labels) == 0:
        return "background", -1, 0.0

    same_class = iou_row * (gt_labels == class_id)
    best_same = int(same_class.argmax())
    best_same_iou = float(same_class[best_same])
    best_any = int(iou_row.argmax())
    best_any_iou = float(iou_row[best_any])

    if best_same_iou >= iou_threshold:
        return "duplicate", best_same, best_same_iou
    if best_same_iou >= LOCALIZATION_IOU_FLOOR:
        return "poor_localization", best_same, best_same_iou
    if best_any_iou >= iou_threshold:
        return "wrong_class", best_any, best_any_iou
    return "background", -1, best_same_iou


def classify_image(
    pred_boxes: np.ndarray,
    pred_scores: np.ndarray,
    pred_labels: np.ndarray,
    gt_boxes: np.ndarray,
    gt_labels: np.ndarray,
    iou_threshold: float,
    class_names: Sequence[str],
) -> List[Dict]:
    """Diagnose every box in one image.

    Produces one record per prediction and one per missed ground-truth box,
    each tagged with an `error_type` that says what kind of mistake it is:

    - ``correct``           — matched a same-class box at or above the threshold
    - ``duplicate``         — a second prediction on an object already found
    - ``poor_localization``  — right class, box too loose to count
    - ``wrong_class``       — found a real object, labelled it wrong
    - ``background``        — invented on empty background
    - ``missed``            — a ground-truth box nothing claimed

    The split matters because the fixes differ: `wrong_class` and
    `poor_localization` are label-quality and regression problems, while
    `background` is the only one that is purely a detection failure.
    """

    def name_of(class_id: int) -> Optional[str]:
        if 0 <= class_id < len(class_names):
            return class_names[class_id]
        return None

    pred_to_gt, gt_to_pred, pred_iou = greedy_match(
        pred_boxes, pred_scores, pred_labels, gt_boxes, gt_labels, iou_threshold
    )

    iou_all = box_iou(pred_boxes, gt_boxes) if len(pred_boxes) and len(gt_boxes) else None
    records: List[Dict] = []

    for pred_idx in range(len(pred_boxes)):
        class_id = int(pred_labels[pred_idx])
        record = {
            "outcome": "tp",
            "error_type": "correct",
            "pred_class": class_id,
            "pred_class_name": name_of(class_id),
            "gt_class": None,
            "gt_class_name": None,
            "confidence": float(pred_scores[pred_idx]),
            "iou": float(pred_iou[pred_idx]),
            "box": [float(v) for v in pred_boxes[pred_idx]],
            "gt_box": None,
        }

        gt_idx = int(pred_to_gt[pred_idx])
        if gt_idx >= 0:
            record["gt_class"] = int(gt_labels[gt_idx])
            record["gt_class_name"] = name_of(int(gt_labels[gt_idx]))
            record["gt_box"] = [float(v) for v in gt_boxes[gt_idx]]
            records.append(record)
            continue

        record["outcome"] = "fp"
        error_type, blame, blame_iou = _diagnose_false_positive(
            iou_all[pred_idx] if iou_all is not None else None,
            class_id, gt_labels, iou_threshold,
        )
        record["error_type"] = error_type
        record["iou"] = blame_iou
        if blame >= 0:
            record["gt_class"] = int(gt_labels[blame])
            record["gt_class_name"] = name_of(int(gt_labels[blame]))
            record["gt_box"] = [float(v) for v in gt_boxes[blame]]
        records.append(record)

    for gt_idx in range(len(gt_boxes)):
        if gt_to_pred[gt_idx] >= 0:
            continue
        class_id = int(gt_labels[gt_idx])
        records.append({
            "outcome": "fn",
            "error_type": "missed",
            "pred_class": None,
            "pred_class_name": None,
            "gt_class": class_id,
            "gt_class_name": name_of(class_id),
            "confidence": None,
            "iou": None,
            "box": None,
            "gt_box": [float(v) for v in gt_boxes[gt_idx]],
        })

    return records


# ── Aggregates ───────────────────────────────────────────────────────────────


def build_confusion_matrix(
    per_image: Sequence[Dict], n_classes: int, iou_threshold: float
) -> Dict:
    """Confusion matrix over classes plus a background row and column.

    ``matrix[gt][pred]``, with index ``n_classes`` standing for background: the
    last column counts ground truth nothing found, the last row counts
    predictions with no object behind them. Reading a row tells you what a
    class gets confused with; reading a column tells you what gets mistaken
    for it.

    Boxes are paired *class-agnostically* here, unlike in scoring. That is the
    whole point of the matrix: a car labelled 'truck' should appear at
    ``matrix[car][truck]``, not as a missed car plus an invented truck. It also
    keeps the counts honest — every ground-truth box and every prediction is
    counted exactly once, so rows sum to the ground-truth count per class and
    columns to the prediction count.
    """
    size = n_classes + 1
    background = n_classes
    matrix = [[0] * size for _ in range(size)]

    def slot(class_id) -> int:
        if class_id is None or not 0 <= int(class_id) < n_classes:
            return background
        return int(class_id)

    for item in per_image:
        boxes = item["boxes"]
        scores = item["scores"]
        labels = item["labels"]
        gt_boxes = item["gt_boxes"]
        gt_labels = item["gt_labels"]

        pred_to_gt, gt_to_pred, _ = greedy_match(
            boxes, scores, labels, gt_boxes, gt_labels,
            iou_threshold, class_agnostic=True,
        )

        for pred_idx in range(len(boxes)):
            gt_idx = int(pred_to_gt[pred_idx])
            row = slot(gt_labels[gt_idx]) if gt_idx >= 0 else background
            matrix[row][slot(labels[pred_idx])] += 1

        for gt_idx in range(len(gt_boxes)):
            if gt_to_pred[gt_idx] < 0:
                matrix[slot(gt_labels[gt_idx])][background] += 1

    return {
        "matrix": matrix,
        "labels": list(range(n_classes)) + [-1],
        "background_index": background,
    }


def threshold_sweep(
    per_image: Sequence[Dict],
    iou_threshold: float,
    thresholds: Sequence[float] = SWEEP_THRESHOLDS,
) -> List[Dict]:
    """Precision/recall/F1 across confidence levels.

    Turns "what should I deploy at?" into a measurement. Each entry re-counts
    the whole split with predictions below that confidence dropped, so the
    numbers are the ones the deployed model would actually produce.
    """
    sweep: List[Dict] = []
    for conf in thresholds:
        tp = fp = fn = 0
        for item in per_image:
            keep = item["scores"] >= conf
            image_tp, image_fp, image_fn = count_outcomes(
                item["boxes"][keep],
                item["scores"][keep],
                item["labels"][keep],
                item["gt_boxes"],
                item["gt_labels"],
                iou_threshold,
            )
            tp += image_tp
            fp += image_fp
            fn += image_fn
        precision = tp / max(tp + fp, _EPS)
        recall = tp / max(tp + fn, _EPS)
        sweep.append({
            "conf": float(conf),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(2 * precision * recall / max(precision + recall, _EPS)),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        })
    return sweep


# ── Persistence ──────────────────────────────────────────────────────────────


def _update_run(run_id: str, **fields) -> None:
    """Patch an evaluation_runs row. Used for progress, so it must not raise."""
    if not fields:
        return
    connection = get_db_connection()
    if not connection:
        return
    try:
        assignments = ", ".join(f"{column} = %s" for column in fields)
        cursor = connection.cursor()
        cursor.execute(
            f"UPDATE evaluation_runs SET {assignments} WHERE id = %s",
            (*fields.values(), run_id),
        )
        connection.commit()
        cursor.close()
    except Exception as exc:
        logger.error(f"evaluation: failed to update run {run_id}: {exc}")
    finally:
        try:
            connection.close()
        except Exception:
            pass


def load_split(version_id: str, split: str) -> List[Dict]:
    """Read one split of a version snapshot as evaluation inputs.

    The version snapshot is the ground truth that training actually consumed —
    post-preprocessing, post-augmentation, with the split already assigned — so
    it is read instead of the live `annotations` table, which has moved on since
    the version was frozen.
    """
    connection = get_db_connection()
    if not connection:
        return []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, original_image_id, filename, path, width, height, boxes
            FROM dataset_version_images
            WHERE version_id = %s AND split = %s
            ORDER BY filename
            """,
            (version_id, split),
        )
        rows = cursor.fetchall()
        cursor.close()
    except Exception as exc:
        logger.error(f"evaluation: failed to load split {split} of {version_id}: {exc}")
        return []
    finally:
        try:
            connection.close()
        except Exception:
            pass

    items: List[Dict] = []
    for row in rows:
        boxes = row.get("boxes")
        if isinstance(boxes, (str, bytes)):
            try:
                boxes = json.loads(boxes)
            except (ValueError, TypeError):
                boxes = []
        width = int(row.get("width") or 0)
        height = int(row.get("height") or 0)
        if width <= 0 or height <= 0:
            # Normalised ground truth cannot be placed without dimensions.
            logger.warning(f"evaluation: skipping {row.get('filename')} — no dimensions")
            continue
        gt_boxes, gt_labels = gt_to_xyxy(boxes or [], width, height)
        items.append({
            "image_id": row.get("original_image_id"),
            "filename": row["filename"],
            "path": row.get("path"),
            "width": width,
            "height": height,
            "gt_boxes": gt_boxes,
            "gt_labels": gt_labels,
        })
    return items


def _persist_image_rows(run_id: str, rows: Sequence[Tuple]) -> None:
    if not rows:
        return
    connection = get_db_connection()
    if not connection:
        raise RuntimeError("no database connection for evaluation image rows")
    try:
        cursor = connection.cursor()
        cursor.executemany(
            """
            INSERT INTO evaluation_images
                (run_id, image_id, filename, path, width, height,
                 tp_count, fp_count, fn_count, gt_count, pred_count, error_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        connection.commit()
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _persist_prediction_rows(rows: Sequence[Tuple]) -> None:
    if not rows:
        return
    connection = get_db_connection()
    if not connection:
        raise RuntimeError("no database connection for evaluation prediction rows")
    try:
        cursor = connection.cursor()
        for start in range(0, len(rows), _INSERT_CHUNK):
            cursor.executemany(
                """
                INSERT INTO evaluation_predictions
                    (run_id, image_id, filename, outcome, error_type,
                     pred_class, pred_class_name, gt_class, gt_class_name,
                     confidence, iou, box, gt_box)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows[start:start + _INSERT_CHUNK],
            )
            connection.commit()
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ── Orchestration ────────────────────────────────────────────────────────────


def create_run(
    dataset_id: str,
    version_id: str,
    model_name: str,
    job_id: Optional[str],
    split: str,
    conf_threshold: float,
    iou_threshold: float,
    created_by: Optional[int],
) -> Optional[str]:
    """Insert a pending evaluation run and return its id."""
    run_id = str(uuid.uuid4())
    connection = get_db_connection()
    if not connection:
        return None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO evaluation_runs
                (id, dataset_id, version_id, model_name, job_id, split,
                 status, conf_threshold, iou_threshold, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
            """,
            (
                run_id, dataset_id, version_id, model_name, job_id, split,
                conf_threshold, iou_threshold, created_by,
            ),
        )
        connection.commit()
        cursor.close()
        return run_id
    except Exception as exc:
        logger.error(f"evaluation: failed to create run: {exc}")
        return None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _predict_batch(model, paths: Sequence[str], run_id: str) -> List[List[Dict]]:
    """Predict a batch, falling back to one image at a time.

    A whole batch failing on one unreadable file would cost the other fifteen
    images, so a batch failure retries individually and an image that still
    fails is scored as "found nothing" — a recorded miss, which is the truth,
    rather than a silently shorter split.

    `_NMS_IOU` is the overlap used while decoding boxes. It is deliberately not
    the run's `iou_threshold`, which decides whether a prediction *matches*
    ground truth; conflating the two would let the match criterion change what
    the model even returned.
    """
    try:
        detected = model.predict_batch(
            paths, conf_threshold=METRIC_SCORE_FLOOR, iou_threshold=_NMS_IOU
        )
        # Callers zip this against `paths`, which would silently drop images if
        # a backend ever returned a shorter list. Pad instead, so a backend bug
        # shows up as images that found nothing rather than as a split that
        # quietly shrank. `strict=` would say this better but needs Python 3.10,
        # and the supported floor here is 3.9.
        if len(detected) != len(paths):
            logger.error(
                f"evaluation {run_id}: backend returned {len(detected)} results "
                f"for {len(paths)} images; padding the difference"
            )
            detected = list(detected)[:len(paths)]
            detected += [[] for _ in range(len(paths) - len(detected))]
        return detected
    except Exception as exc:
        logger.warning(f"evaluation {run_id}: a batch failed ({exc}); retrying per image")

    detections: List[List[Dict]] = []
    for path in paths:
        try:
            detections.append(
                model.predict(path, conf_threshold=METRIC_SCORE_FLOOR, iou_threshold=_NMS_IOU)
            )
        except Exception as exc:
            logger.error(f"evaluation {run_id}: {path} failed ({exc}); scored as no detections")
            detections.append([])
    return detections


def run_evaluation(
    run_id: str,
    model_path: str,
    model_type: str,
    version_id: str,
    split: str,
    class_names: Sequence[str],
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.5,
) -> Dict:
    """Score a model over one split and persist everything the UI needs.

    Runs synchronously; callers put it on a background thread. Failures are
    recorded on the run row rather than raised, so a crashed evaluation shows
    up in the UI as a failed run with a reason instead of vanishing.
    """
    try:
        return _run_evaluation_inner(
            run_id, model_path, model_type, version_id, split,
            class_names, conf_threshold, iou_threshold,
        )
    except Exception as exc:
        logger.exception(f"evaluation run {run_id} failed")
        _update_run(run_id, status="failed", error_message=str(exc)[:1000], progress=100)
        return {"status": "failed", "error": str(exc)}


def _run_evaluation_inner(
    run_id: str,
    model_path: str,
    model_type: str,
    version_id: str,
    split: str,
    class_names: Sequence[str],
    conf_threshold: float,
    iou_threshold: float,
) -> Dict:
    from app.services.trainer_factory import create_inference

    _update_run(run_id, status="running", progress=0)

    items = load_split(version_id, split)
    if not items:
        raise ValueError(
            f"Version has no images in the '{split}' split. Generate a version "
            f"with a {split} split, or evaluate against a different one."
        )

    class_names = list(class_names)
    class_index = {name: idx for idx, name in enumerate(class_names)}
    model = create_inference(model_path, model_type)

    per_image: List[Dict] = []
    image_rows: List[Tuple] = []
    prediction_rows: List[Tuple] = []
    per_image_at_threshold: List[Dict] = []
    totals = {"tp": 0, "fp": 0, "fn": 0, "gt": 0, "pred": 0}
    class_errors: Dict[int, Dict[str, int]] = {}

    for start in range(0, len(items), _BATCH_SIZE):
        batch = items[start:start + _BATCH_SIZE]
        paths = [item["path"] for item in batch]
        batch_detections = _predict_batch(model, paths, run_id)

        for item, detections in zip(batch, batch_detections):
            boxes, scores, labels = predictions_to_arrays(detections, class_index)
            per_image.append({
                "boxes": boxes,
                "scores": scores,
                "labels": labels,
                "gt_boxes": item["gt_boxes"],
                "gt_labels": item["gt_labels"],
            })

            # The error breakdown describes one operating point, so it sees only
            # the predictions the deployed model would have surfaced.
            keep = scores >= conf_threshold
            records = classify_image(
                boxes[keep], scores[keep], labels[keep],
                item["gt_boxes"], item["gt_labels"],
                iou_threshold, class_names,
            )
            per_image_at_threshold.append({
                "boxes": boxes[keep],
                "scores": scores[keep],
                "labels": labels[keep],
                "gt_boxes": item["gt_boxes"],
                "gt_labels": item["gt_labels"],
            })

            tp = sum(1 for r in records if r["outcome"] == "tp")
            fp = sum(1 for r in records if r["outcome"] == "fp")
            fn = sum(1 for r in records if r["outcome"] == "fn")
            gt_count = len(item["gt_labels"])
            pred_count = int(keep.sum())

            totals["tp"] += tp
            totals["fp"] += fp
            totals["fn"] += fn
            totals["gt"] += gt_count
            totals["pred"] += pred_count

            for record in records:
                blame = record.get("gt_class")
                if blame is None:
                    blame = record.get("pred_class")
                if blame is None or blame < 0:
                    continue
                bucket = class_errors.setdefault(blame, {"tp": 0, "fp": 0, "fn": 0})
                bucket[record["outcome"]] += 1

            image_rows.append((
                run_id, item["image_id"], item["filename"], item["path"],
                item["width"], item["height"],
                tp, fp, fn, gt_count, pred_count, float(fp + fn),
            ))
            for record in records:
                prediction_rows.append((
                    run_id, item["image_id"], item["filename"],
                    record["outcome"], record["error_type"],
                    record["pred_class"], record["pred_class_name"],
                    record["gt_class"], record["gt_class_name"],
                    record["confidence"], record["iou"],
                    json.dumps(record["box"]) if record["box"] is not None else None,
                    json.dumps(record["gt_box"]) if record["gt_box"] is not None else None,
                ))

        # Reserve the last slice of the bar for scoring and the DB writes.
        _update_run(run_id, progress=min(90, int(90 * (start + len(batch)) / len(items))))

    scored = evaluate_detections(
        [{"boxes": p["boxes"], "scores": p["scores"], "labels": p["labels"]} for p in per_image],
        [{"boxes": p["gt_boxes"], "labels": p["gt_labels"]} for p in per_image],
        dict(enumerate(class_names)),
    )

    precision = totals["tp"] / max(totals["tp"] + totals["fp"], _EPS)
    recall = totals["tp"] / max(totals["tp"] + totals["fn"], _EPS)
    metrics = {
        "map50": scored["metrics"]["map50"],
        "map50_95": scored["metrics"]["map50-95"],
        # At the run's operating point, from counted outcomes.
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(2 * precision * recall / max(precision + recall, _EPS)),
        "tp": totals["tp"],
        "fp": totals["fp"],
        "fn": totals["fn"],
        # From the full PR curve, at each class's best-F1 point.
        "curve_precision": scored["metrics"]["precision"],
        "curve_recall": scored["metrics"]["recall"],
        "sweep": threshold_sweep(per_image, iou_threshold),
    }

    per_class = []
    for entry in scored["per_class_metrics"]:
        counts = class_errors.get(entry["class_id"], {"tp": 0, "fp": 0, "fn": 0})
        per_class.append({**entry, **counts})

    confusion = build_confusion_matrix(
        per_image_at_threshold, len(class_names), iou_threshold
    )

    _update_run(run_id, progress=95)
    _persist_image_rows(run_id, image_rows)
    _persist_prediction_rows(prediction_rows)

    _update_run(
        run_id,
        status="completed",
        progress=100,
        total_images=len(items),
        gt_count=totals["gt"],
        pred_count=totals["pred"],
        metrics=json.dumps(metrics),
        per_class_metrics=json.dumps(per_class),
        confusion_matrix=json.dumps(confusion),
        class_names=json.dumps(class_names),
        error_message=None,
    )
    return {"status": "completed", "metrics": metrics}
