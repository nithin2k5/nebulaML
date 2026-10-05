"""
Evaluation workbench: run a trained model against a held-out split and make
its mistakes browsable.

The training tab already reports mAP and ships YOLO's confusion-matrix PNG.
Neither tells you *which* images are wrong or *how*, which is the question that
leads to a fix. This module runs the model over a split, classifies every
prediction and every miss, and stores the result so the client can ask:

    show me images where the model hallucinated a truck, worst first

It also serves the two readings a single mAP number cannot give: a
confidence sweep (where should the threshold sit for deployment?) and a
per-class diff between two runs (what did the last change actually cost?).
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.db.session import db_cursor
from app.services import error_analysis as ea
from app.services.database import AnnotationService, DatasetService
from app.services.detection_metrics import evaluate_detections

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[4]
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

# Evaluating a split means one forward pass per image, so it runs in the
# background with the same in-memory progress dict the other long jobs use.
evaluation_jobs: Dict[str, Dict[str, Any]] = {}

_TERMINAL_STATUSES = {"completed", "failed"}
_FINISHED_JOB_RETENTION = 20

# A guard on the default run rather than a hard limit: a 50k-image test split
# would otherwise tie up a worker for an hour by accident.
DEFAULT_MAX_IMAGES = 500

# Images per forward pass. One call per image left the GPU idle between
# launches; a batch amortises that over sixteen.
_BATCH_SIZE = 16

# Inference floor for the metric pass. mAP is threshold-free, so the curve has
# to be built from predictions well below the operating point — filtering to
# conf_threshold first would truncate it and understate AP.
_SCORE_FLOOR = 0.01

_SORTABLE = {
    # Worst-first is the useful default, so precision ascending comes first.
    "precision": "precision_score ASC, fp DESC",
    "recall": "recall_score ASC, fn DESC",
    "errors": "(fp + fn) DESC",
    "false_positives": "fp DESC",
    "false_negatives": "fn DESC",
}

_KIND_COLUMNS = {
    "background": "n_background",
    "wrong_class": "n_wrong_class",
    "poor_localisation": "n_poor_localisation",
    "duplicate": "n_duplicate",
    "missed": "n_missed",
}


def _prune_finished_jobs(jobs: Dict[str, Dict], keep: int = _FINISHED_JOB_RETENTION) -> None:
    """Drop all but the most recent `keep` finished jobs, oldest first."""
    finished = [
        job_id for job_id, job in jobs.items()
        if job.get("status") in _TERMINAL_STATUSES
    ]
    for job_id in finished[:-keep] if keep else finished:
        jobs.pop(job_id, None)


class EvaluateRequest(BaseModel):
    job_id: str
    # Which split to score against. "test" is the honest choice — val was used
    # for early stopping during training, so it is no longer truly held out —
    # but small datasets often have no test split, hence the fallback.
    split: str = Field("test", pattern="^(test|val|train)$")
    iou_threshold: float = Field(0.5, ge=0.05, le=0.95)
    conf_threshold: float = Field(0.25, ge=0.0, le=0.99)
    max_images: int = Field(DEFAULT_MAX_IMAGES, ge=1, le=5000)


def _resolve_weights(job_id: str) -> Optional[Path]:
    """Locate a job's best weights, preferring the native .pt checkpoint."""
    weights_dir = (_RUNS_BASE / f"job_{job_id}" / "weights").resolve()
    # Containment check: job_id reaches this from the request body.
    if not str(weights_dir).startswith(str(_RUNS_BASE)):
        return None
    for name in ("best.pt", "best.onnx", "last.pt"):
        candidate = weights_dir / name
        if candidate.exists():
            return candidate
    return None


def _owned_job(job_id: str, current_user: dict) -> Dict[str, Any]:
    """
    Fetch a training job the caller may see.

    Delegates to the training module so there is exactly one definition of
    "may this user see this job", including the persisted-job reload that
    makes pre-restart jobs addressable.
    """
    from app.api.v1.endpoints.training import _get_owned_job

    return _get_owned_job(job_id, current_user)


def _class_names_for(dataset: Dict) -> Dict[int, str]:
    """Label id -> name, in the dataset's own class order."""
    return dict(enumerate(dataset.get("classes") or []))


def _split_images(dataset: Dict, split: str) -> Tuple[List[Dict], str]:
    """
    Images in a split, with the split actually used.

    Falls back test -> val -> every annotated image, because a project that
    never ran the split step still deserves an answer. The caller reports
    which one it got, so a number is never silently from the training data.
    """
    images = dataset.get("images") or []

    for candidate in (split, "val", "valid"):
        chosen = [img for img in images if (img.get("split") or "") == candidate]
        if chosen:
            return chosen, candidate

    return [img for img in images if img.get("annotated")], "all-annotated"


def _store_evaluation(evaluation_id: str, fields: Dict[str, Any]) -> None:
    """Update one evaluation row with whatever fields are given."""
    if not fields:
        return
    assignments = ", ".join(f"{column} = %s" for column in fields)
    values = list(fields.values()) + [evaluation_id]
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE evaluations SET {assignments} WHERE id = %s", values
            )
    except Exception as e:
        logger.error(f"Could not update evaluation {evaluation_id}: {e}")


def _predict_batch(model: Any, paths: List[str]) -> List[Optional[List[Dict]]]:
    """
    Predict a batch, falling back to one image at a time.

    A whole batch failing on a single unreadable file would cost the other
    fifteen, so a batch error retries individually and an image that still
    fails comes back as None for the caller to skip. A backend returning a
    short list is padded rather than zipped against the wrong images.
    """
    try:
        detections = model.predict_batch(paths, conf_threshold=_SCORE_FLOOR)
        if len(detections) == len(paths):
            return list(detections)
        logger.error(
            f"Evaluation: backend returned {len(detections)} results for "
            f"{len(paths)} images; padding the difference"
        )
        padded = list(detections)[: len(paths)]
        return padded + [None] * (len(paths) - len(padded))
    except Exception as e:
        logger.warning(f"Evaluation: a batch failed ({e}); retrying per image")

    results: List[Optional[List[Dict]]] = []
    for path in paths:
        try:
            results.append(model.predict(path, conf_threshold=_SCORE_FLOOR))
        except Exception as e:
            logger.warning(f"Evaluation: inference failed on {path}: {e}")
            results.append(None)
    return results


def _score_split(
    model: Any,
    evaluation_id: str,
    dataset_id: str,
    images: List[Dict],
    annotations: Dict[str, List[Dict]],
    class_names: Dict[int, str],
    request: EvaluateRequest,
    progress: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple]]:
    """
    Run the model over a split and classify each image's errors.

    Returns (predictions, targets, per_image_rows) where the first two feed the
    aggregate metrics and the third is ready for a bulk insert. An image that
    cannot be read or inferred is skipped rather than aborting the run — one
    corrupt file should not cost a 500-image evaluation.
    """
    predictions: List[Dict[str, Any]] = []
    targets: List[Dict[str, Any]] = []
    per_image_rows: List[Tuple] = []

    # Readable files only, so a batch is never short and the zip below cannot
    # drift out of step with its images.
    readable: List[Tuple[Dict, Path]] = []
    for image in images:
        path = Path(image.get("path") or "")
        if not path.is_absolute():
            path = Path("datasets") / dataset_id / "images" / image["filename"]
        if not path.exists():
            logger.warning(f"Evaluation: missing file for image {image['id']}")
            continue
        readable.append((image, path))

    index = -1
    for start in range(0, len(readable), _BATCH_SIZE):
        batch = readable[start:start + _BATCH_SIZE]
        batch_detections = _predict_batch(model, [str(path) for _, path in batch])

        for (image, path), detections in zip(batch, batch_detections):
            index += 1
            if detections is None:
                logger.warning(f"Evaluation: inference failed on {path}")
                continue

            prediction = ea.detections_to_arrays(detections)
            target = ea.gt_boxes_to_xyxy(annotations.get(image["id"], []))

            predictions.append(prediction)
            targets.append(target)

            detail = ea.classify_image_errors(
                prediction,
                target,
                iou_threshold=request.iou_threshold,
                conf_threshold=request.conf_threshold,
                class_names=class_names,
            )
            counts = detail["counts"]
            by_kind = counts["by_kind"]

            per_image_rows.append((
                evaluation_id,
                image["id"],
                image.get("filename"),
                counts["tp"],
                counts["fp"],
                counts["fn"],
                counts["precision"],
                counts["recall"],
                by_kind.get("background", 0),
                by_kind.get("wrong_class", 0),
                by_kind.get("poor_localisation", 0),
                by_kind.get("duplicate", 0),
                by_kind.get("missed", 0),
                json.dumps(detail),
            ))

            if progress is not None:
                progress["progress"] = index + 1

    return predictions, targets, per_image_rows


def _persist_results(
    evaluation_id: str,
    split_used: str,
    predictions: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
    per_image_rows: List[Tuple],
    class_names: Dict[int, str],
    iou_threshold: float,
    conf_threshold: float,
) -> None:
    """
    Compute the aggregates and write both the summary and the per-image rows.

    `evaluate_detections` gives the COCO-style numbers; the error analysis gives
    the breakdown you can act on. The detail insert is allowed to fail without
    failing the evaluation — the aggregates are still worth keeping.
    """
    summary = evaluate_detections(predictions, targets, class_names)
    per_image_details = [json.loads(row[-1]) for row in per_image_rows]
    sweep = ea.confidence_sweep(predictions, targets, iou_threshold=iou_threshold)
    matrix = ea.confusion_matrix(
        predictions,
        targets,
        n_classes=len(class_names),
        iou_threshold=iou_threshold,
        conf_threshold=conf_threshold,
    )

    if per_image_rows:
        try:
            with db_cursor(commit=True) as cursor:
                cursor.executemany(
                    "INSERT INTO evaluation_images "
                    "(evaluation_id, image_id, filename, tp, fp, fn, "
                    " precision_score, recall_score, n_background, "
                    " n_wrong_class, n_poor_localisation, n_duplicate, "
                    " n_missed, details) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "  tp = VALUES(tp), fp = VALUES(fp), fn = VALUES(fn), "
                    "  precision_score = VALUES(precision_score), "
                    "  recall_score = VALUES(recall_score), "
                    "  n_background = VALUES(n_background), "
                    "  n_wrong_class = VALUES(n_wrong_class), "
                    "  n_poor_localisation = VALUES(n_poor_localisation), "
                    "  n_duplicate = VALUES(n_duplicate), "
                    "  n_missed = VALUES(n_missed), "
                    "  details = VALUES(details)",
                    per_image_rows,
                )
        except Exception as e:
            logger.error(f"Could not store per-image evaluation detail: {e}")

    _store_evaluation(evaluation_id, {
        "status": "completed",
        "split": split_used,
        "images_evaluated": len(predictions),
        "metrics": json.dumps(summary.get("metrics", {})),
        "per_class_metrics": json.dumps(summary.get("per_class_metrics", [])),
        "error_kinds": json.dumps(ea.aggregate_error_kinds(per_image_details)),
        "class_confusion": json.dumps(ea.class_confusion(per_image_details)),
        "confusion_matrix": json.dumps(matrix),
        "confidence_sweep": json.dumps(sweep),
        "best_operating_point": json.dumps(ea.best_operating_point(sweep) or {}),
    })


def _evaluate_task(
    evaluation_id: str,
    job_id: str,
    dataset_id: str,
    request: EvaluateRequest,
) -> None:
    """Score a split and persist per-image error detail. Runs in the background."""
    progress = evaluation_jobs.get(evaluation_id)

    def mark(status: str, **extra: Any) -> None:
        if progress is not None:
            progress["status"] = status
            progress.update(extra)

    mark("running")
    try:
        from app.api.v1.endpoints.inference import _get_job_model_type
        from app.services.trainer_factory import create_inference

        weights = _resolve_weights(job_id)
        if weights is None:
            raise RuntimeError("No trained weights found for this job")

        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise RuntimeError("Dataset not found")

        class_names = _class_names_for(dataset)
        images, split_used = _split_images(dataset, request.split)
        images = images[: request.max_images]
        if not images:
            raise RuntimeError("No images in this split to evaluate")

        # Ground truth, keyed by image, so a missing annotation is an empty
        # target rather than a skipped image: a model predicting boxes on an
        # unlabelled image is making false positives and should be charged for
        # them.
        annotations = {
            row["image_id"]: row.get("boxes") or []
            for row in AnnotationService.get_all_dataset_annotations(dataset_id)
        }

        # The backend has to come from the job. Loading every checkpoint with
        # YOLOInference worked only for YOLO runs — an RT-DETR or torchvision
        # checkpoint is a different format, so those evaluations either threw
        # or, worse, scored whatever ultralytics managed to coerce.
        model = create_inference(str(weights), _get_job_model_type(job_id))

        if progress is not None:
            progress["total"] = len(images)

        predictions, targets, per_image_rows = _score_split(
            model=model,
            evaluation_id=evaluation_id,
            dataset_id=dataset_id,
            images=images,
            annotations=annotations,
            class_names=class_names,
            request=request,
            progress=progress,
        )

        if not predictions:
            raise RuntimeError("No images could be read for evaluation")

        _persist_results(
            evaluation_id=evaluation_id,
            split_used=split_used,
            predictions=predictions,
            targets=targets,
            per_image_rows=per_image_rows,
            class_names=class_names,
            iou_threshold=request.iou_threshold,
            conf_threshold=request.conf_threshold,
        )

        mark("completed", evaluation_id=evaluation_id, images_evaluated=len(predictions))
        logger.info(
            f"Evaluated job {job_id} on {len(predictions)} {split_used} image(s)"
        )
    except Exception as e:
        logger.error(f"Evaluation {evaluation_id} failed: {e}")
        _store_evaluation(evaluation_id, {
            "status": "failed",
            "error_message": str(e),
        })
        mark("failed", error=str(e))


@router.post("/run")
async def run_evaluation(
    request: EvaluateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Evaluate a trained model against a split and index its mistakes."""
    job = _owned_job(request.job_id, current_user)

    dataset_id = job.get("dataset_id")
    if not dataset_id:
        raise HTTPException(
            status_code=400, detail="This job is not linked to a dataset"
        )

    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")

    if _resolve_weights(request.job_id) is None:
        raise HTTPException(
            status_code=409,
            detail="No trained weights for this job yet. Wait for training to finish.",
        )

    evaluation_id = str(uuid.uuid4())
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO evaluations "
                "(id, job_id, dataset_id, split, iou_threshold, conf_threshold, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'pending')",
                (
                    evaluation_id,
                    request.job_id,
                    dataset_id,
                    request.split,
                    request.iou_threshold,
                    request.conf_threshold,
                ),
            )
    except Exception as e:
        logger.error(f"Could not create evaluation row: {e}")
        raise HTTPException(
            status_code=500, detail="Could not start evaluation"
        ) from None

    _prune_finished_jobs(evaluation_jobs)
    evaluation_jobs[evaluation_id] = {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "job_id": request.job_id,
        "evaluation_id": evaluation_id,
    }

    background_tasks.add_task(
        _evaluate_task, evaluation_id, request.job_id, dataset_id, request
    )

    return {
        "success": True,
        "evaluation_id": evaluation_id,
        "message": "Evaluation started in the background",
    }


@router.get("/status/{evaluation_id}")
async def evaluation_status(
    evaluation_id: str, current_user: dict = Depends(get_current_user)
):
    """Poll a running evaluation."""
    in_memory = evaluation_jobs.get(evaluation_id)
    row = _load_evaluation(evaluation_id, current_user)

    return {
        "evaluation_id": evaluation_id,
        "status": row.get("status"),
        "progress": (in_memory or {}).get("progress", row.get("images_evaluated", 0)),
        "total": (in_memory or {}).get("total", row.get("images_evaluated", 0)),
        "error": row.get("error_message"),
    }


def _decode(row: Dict[str, Any], *columns: str) -> Dict[str, Any]:
    """
    Parse the JSON columns of an evaluation row in place.

    mysql-connector returns JSON columns as str on some versions and as parsed
    objects on others, so both have to be tolerated.
    """
    for column in columns:
        value = row.get(column)
        if isinstance(value, (str, bytes, bytearray)):
            try:
                row[column] = json.loads(value)
            except (ValueError, TypeError):
                row[column] = None
    return row


def _load_evaluation(evaluation_id: str, current_user: dict) -> Dict[str, Any]:
    """Fetch an evaluation, asserting the caller may see its training job."""
    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM evaluations WHERE id = %s", (evaluation_id,)
            )
            row = cursor.fetchone()
    except Exception as e:
        logger.error(f"Could not load evaluation {evaluation_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load evaluation") from None

    if not row:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Authorisation rides on the training job, which is the thing that has an
    # owner; an evaluation is just a view of it.
    _owned_job(row["job_id"], current_user)
    return row


@router.get("/latest/{job_id}")
async def latest_evaluation(job_id: str, current_user: dict = Depends(get_current_user)):
    """The most recent completed evaluation for a training job, if any."""
    _owned_job(job_id, current_user)

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM evaluations WHERE job_id = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            )
            row = cursor.fetchone()
    except Exception as e:
        logger.error(f"Could not load latest evaluation for {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load evaluation") from None

    if not row:
        return {"job_id": job_id, "evaluation": None}

    return {
        "job_id": job_id,
        "evaluation": _decode(
            row, "metrics", "per_class_metrics", "error_kinds",
            "class_confusion", "confusion_matrix", "confidence_sweep",
            "best_operating_point",
        ),
    }


@router.get("/{evaluation_id}")
async def get_evaluation(
    evaluation_id: str, current_user: dict = Depends(get_current_user)
):
    """Aggregate results: metrics, per-class, error kinds, confusion, sweep."""
    row = _load_evaluation(evaluation_id, current_user)
    return _decode(
        row, "metrics", "per_class_metrics", "error_kinds",
        "class_confusion", "confusion_matrix", "confidence_sweep",
        "best_operating_point",
    )


@router.get("/{evaluation_id}/images")
async def list_evaluation_images(
    evaluation_id: str,
    kind: Optional[str] = None,
    class_name: Optional[str] = None,
    sort: str = "precision",
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """
    Browse the per-image results.

    `kind` filters to images carrying at least one error of that kind, which is
    the whole point of the feature: "show me every image where a truck was
    called a car" is one query, not a scan.
    """
    _load_evaluation(evaluation_id, current_user)

    if sort not in _SORTABLE:
        raise HTTPException(
            status_code=400,
            detail=f"sort must be one of {', '.join(sorted(_SORTABLE))}",
        )
    if kind and kind not in _KIND_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {', '.join(sorted(_KIND_COLUMNS))}",
        )

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    where = ["evaluation_id = %s"]
    params: List[Any] = [evaluation_id]
    if kind:
        # Column name comes from a fixed map, never from the request string.
        where.append(f"{_KIND_COLUMNS[kind]} > 0")

    sql = (
        "SELECT image_id, filename, tp, fp, fn, precision_score, recall_score, "
        "       n_background, n_wrong_class, n_poor_localisation, "
        "       n_duplicate, n_missed "
        f"FROM evaluation_images WHERE {' AND '.join(where)} "
        f"ORDER BY {_SORTABLE[sort]} LIMIT %s OFFSET %s"
    )

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(sql, (*params, limit, offset))
            rows = cursor.fetchall() or []
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM evaluation_images "
                f"WHERE {' AND '.join(where)}",
                params,
            )
            total = (cursor.fetchone() or {}).get("total", 0)
    except Exception as e:
        logger.error(f"Could not list evaluation images: {e}")
        raise HTTPException(status_code=500, detail="Could not list images") from None

    # Class filtering needs the detail blob, so it happens after the SQL page.
    # It is a refinement of an already-narrow list, not a primary filter.
    if class_name:
        rows = [row for row in rows if _touches_class(evaluation_id, row["image_id"], class_name)]

    return {
        "evaluation_id": evaluation_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "images": rows,
    }


def _touches_class(evaluation_id: str, image_id: str, class_name: str) -> bool:
    """True when an image's errors or hits involve the named class."""
    detail = _load_image_detail(evaluation_id, image_id)
    if not detail:
        return False
    for bucket in ("true_positives", "false_positives", "false_negatives"):
        for record in detail.get(bucket) or []:
            if class_name in (record.get("class_name"), record.get("gt_class_name")):
                return True
    return False


def _load_image_detail(evaluation_id: str, image_id: str) -> Optional[Dict[str, Any]]:
    """The stored TP/FP/FN boxes for one evaluated image."""
    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT details FROM evaluation_images "
                "WHERE evaluation_id = %s AND image_id = %s",
                (evaluation_id, image_id),
            )
            row = cursor.fetchone()
    except Exception as e:
        logger.error(f"Could not load image detail: {e}")
        return None

    if not row:
        return None
    return _decode(row, "details").get("details")


@router.get("/{evaluation_id}/image/{image_id}")
async def get_evaluation_image(
    evaluation_id: str,
    image_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Full detail for one image: every true positive, false positive and miss,
    with boxes, so the client can draw them over the image.
    """
    _load_evaluation(evaluation_id, current_user)

    detail = _load_image_detail(evaluation_id, image_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail="That image is not part of this evaluation"
        )

    return {"evaluation_id": evaluation_id, "image_id": image_id, "detail": detail}


@router.get("/compare/{evaluation_a}/{evaluation_b}")
async def compare_evaluations(
    evaluation_a: str,
    evaluation_b: str,
    metric: str = "mAP50",
    current_user: dict = Depends(get_current_user),
):
    """
    Diff two evaluations per class, worst regression first.

    This is the view that catches the failure an overall mAP comparison hides:
    a run that gains six points on average while losing eleven on one class.
    """
    row_a = _decode(
        _load_evaluation(evaluation_a, current_user), "metrics", "per_class_metrics"
    )
    row_b = _decode(
        _load_evaluation(evaluation_b, current_user), "metrics", "per_class_metrics"
    )

    allowed_metrics = {"mAP50", "mAP50_95", "precision", "recall"}
    if metric not in allowed_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"metric must be one of {', '.join(sorted(allowed_metrics))}",
        )

    per_class = ea.compare_per_class(
        row_a.get("per_class_metrics") or [],
        row_b.get("per_class_metrics") or [],
        metric=metric,
    )

    regressions = [row for row in per_class if row["status"] == "regressed"]

    return {
        "metric": metric,
        "a": {
            "evaluation_id": evaluation_a,
            "job_id": row_a.get("job_id"),
            "split": row_a.get("split"),
            "metrics": row_a.get("metrics") or {},
        },
        "b": {
            "evaluation_id": evaluation_b,
            "job_id": row_b.get("job_id"),
            "split": row_b.get("split"),
            "metrics": row_b.get("metrics") or {},
        },
        "per_class": per_class,
        "summary": {
            "regressed": len(regressions),
            "improved": sum(1 for row in per_class if row["status"] == "improved"),
            # The single line worth putting in a changelog.
            "worst_regression": regressions[0] if regressions else None,
        },
    }


@router.get("/job/{job_id}/history")
async def evaluation_history(
    job_id: str, current_user: dict = Depends(get_current_user)
):
    """Every evaluation of one training job, newest first."""
    _owned_job(job_id, current_user)

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id, split, iou_threshold, conf_threshold, status, "
                "       images_evaluated, metrics, created_at "
                "FROM evaluations WHERE job_id = %s ORDER BY created_at DESC",
                (job_id,),
            )
            rows = cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Could not load evaluation history: {e}")
        raise HTTPException(status_code=500, detail="Could not load history") from None

    return {
        "job_id": job_id,
        "evaluations": [_decode(row, "metrics") for row in rows],
    }
