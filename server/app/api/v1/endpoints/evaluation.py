"""
Evaluation Endpoint

Scores a finished model against a dataset version's split and serves the
results: aggregate metrics, a per-class table, a confusion matrix, a confidence
sweep, and a per-image failure explorer.

This is the step that was missing between Train and Deploy. Training jobs report
their own validation numbers, computed differently per backend, so "is this
model better than the last one?" had no answer. An evaluation run re-scores
through one shared metric path, which makes two runs comparable — and because
every run records the split and thresholds it used, the comparison stays honest.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.db.session import get_db_connection
from app.services.database import DatasetService, DatasetVersionService
from app.services.evaluation import create_run, run_evaluation

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[4]
# Version snapshots live here; the failure explorer serves images from inside it.
_VERSIONS_BASE = (_SERVER_ROOT / "uploads" / "versions").resolve()

_VALID_SPLITS = ("train", "val", "test")
_VALID_ERROR_TYPES = (
    "correct", "duplicate", "wrong_class", "poor_localization", "background", "missed",
)
_MAX_PAGE_SIZE = 200


class EvaluateRequest(BaseModel):
    dataset_id: str
    version_id: str
    job_id: str
    split: str = "test"
    conf_threshold: float = Field(0.25, ge=0.0, le=1.0)
    iou_threshold: float = Field(0.5, gt=0.0, le=1.0)

    @validator("split")
    def _known_split(cls, value):
        if value not in _VALID_SPLITS:
            raise ValueError(f"split must be one of {_VALID_SPLITS}")
        return value


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_JSON_COLUMNS = ("metrics", "per_class_metrics", "confusion_matrix", "class_names")


def _decode_json_columns(row: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the JSON columns of an evaluation_runs row in place.

    mysql-connector returns JSON columns as str on some versions and as the
    decoded object on others, so both are handled rather than assuming one.
    """
    for column in _JSON_COLUMNS:
        value = row.get(column)
        if isinstance(value, (str, bytes)):
            try:
                row[column] = json.loads(value)
            except (ValueError, TypeError):
                row[column] = None
    return row


def _fetch_run(run_id: str) -> Optional[Dict[str, Any]]:
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM evaluation_runs WHERE id = %s", (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return _decode_json_columns(row) if row else None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _authorize_run(run_id: str, current_user: dict, minimum: str = "viewer") -> Dict[str, Any]:
    """Load a run and confirm the caller may see the project behind it.

    Runs are addressed by their own id, so permission has to be resolved
    through the dataset each one belongs to — otherwise a run id would be a
    bearer token for someone else's metrics.
    """
    run = _fetch_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    dataset = DatasetService.get_dataset(run["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(run["dataset_id"], current_user["id"], dataset["user_id"], minimum)
    return run


def _error_type_counts(run_id: str) -> Dict[str, int]:
    """How many boxes fell into each error bucket, for the run summary."""
    connection = get_db_connection()
    if not connection:
        return {}
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT error_type, COUNT(*) AS n
            FROM evaluation_predictions
            WHERE run_id = %s
            GROUP BY error_type
            """,
            (run_id,),
        )
        counts = {row["error_type"]: int(row["n"]) for row in cursor.fetchall()}
        cursor.close()
        return counts
    except Exception as exc:
        logger.error(f"evaluation: error-type counts failed for {run_id}: {exc}")
        return {}
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/run")
async def start_evaluation(
    request: EvaluateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Queue an evaluation of a trained model against one split of a version."""
    from app.api.v1.endpoints.inference import _get_job_model_type, _resolve_job_weights

    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(request.dataset_id, current_user["id"], dataset["user_id"], "annotator")

    version = DatasetVersionService.get_version(request.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    if version["dataset_id"] != request.dataset_id:
        # Otherwise a caller with access to one project could score a model
        # against a version belonging to another.
        raise HTTPException(status_code=400, detail="Version does not belong to this dataset")

    in_split = [img for img in version.get("images", []) if img.get("split") == request.split]
    if not in_split:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This version has no images in the '{request.split}' split. "
                f"Generate a version that reserves one, or evaluate a different split."
            ),
        )

    # Raises 400/404 itself if the job is unknown or its weights are missing.
    model_path = _resolve_job_weights(request.job_id)
    model_type = _get_job_model_type(request.job_id)

    run_id = create_run(
        dataset_id=request.dataset_id,
        version_id=request.version_id,
        model_name=request.job_id,
        job_id=request.job_id,
        split=request.split,
        conf_threshold=request.conf_threshold,
        iou_threshold=request.iou_threshold,
        created_by=current_user["id"],
    )
    if not run_id:
        raise HTTPException(status_code=500, detail="Could not create the evaluation run")

    background_tasks.add_task(
        run_evaluation,
        run_id,
        model_path,
        model_type,
        request.version_id,
        request.split,
        dataset.get("classes", []),
        request.conf_threshold,
        request.iou_threshold,
    )

    return {
        "run_id": run_id,
        "status": "pending",
        "total_images": len(in_split),
        "message": f"Evaluating {len(in_split)} {request.split} images in the background",
    }


@router.get("/runs/{dataset_id}")
async def list_evaluation_runs(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Every evaluation run for a project, newest first."""
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT r.id, r.dataset_id, r.version_id, r.model_name, r.job_id, r.split,
                   r.status, r.progress, r.conf_threshold, r.iou_threshold,
                   r.total_images, r.gt_count, r.pred_count, r.metrics,
                   r.error_message, r.created_at,
                   v.version_number, v.name AS version_name
            FROM evaluation_runs r
            LEFT JOIN dataset_versions v ON v.id = r.version_id
            WHERE r.dataset_id = %s
            ORDER BY r.created_at DESC
            """,
            (dataset_id,),
        )
        runs = [_decode_json_columns(row) for row in cursor.fetchall()]
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass

    # The sweep is long and the list view never plots it.
    for run in runs:
        if isinstance(run.get("metrics"), dict):
            run["metrics"] = {k: v for k, v in run["metrics"].items() if k != "sweep"}

    return {"dataset_id": dataset_id, "total": len(runs), "runs": runs}


@router.get("/run/{run_id}")
async def get_evaluation_run(run_id: str, current_user: dict = Depends(get_current_user)):
    """One run in full: metrics, per-class table, confusion matrix, error mix."""
    run = _authorize_run(run_id, current_user)
    sweep = []
    if isinstance(run.get("metrics"), dict):
        sweep = run["metrics"].pop("sweep", [])
    return {
        **run,
        "error_types": _error_type_counts(run_id) if run["status"] == "completed" else {},
        "has_sweep": bool(sweep),
    }


@router.get("/run/{run_id}/threshold-sweep")
async def get_threshold_sweep(run_id: str, current_user: dict = Depends(get_current_user)):
    """Precision/recall/F1 across confidence levels.

    This is what turns the deployment threshold from a guess into a choice:
    every level is the whole split re-counted with weaker predictions dropped.
    """
    run = _authorize_run(run_id, current_user)
    metrics = run.get("metrics") or {}
    sweep = metrics.get("sweep") or []
    best = max(sweep, key=lambda entry: entry["f1"]) if sweep else None
    return {
        "run_id": run_id,
        "iou_threshold": run["iou_threshold"],
        "conf_threshold": run["conf_threshold"],
        "sweep": sweep,
        "best_f1": best,
    }


@router.get("/run/{run_id}/errors")
async def list_error_images(
    run_id: str,
    error_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Images ranked by how badly the model did on them.

    Ranked by false positives plus false negatives, so the first page is the
    most informative place to start looking — and with `error_type`, the images
    exhibiting one specific kind of mistake.
    """
    _authorize_run(run_id, current_user)
    if error_type is not None and error_type not in _VALID_ERROR_TYPES:
        raise HTTPException(
            status_code=400, detail=f"error_type must be one of {_VALID_ERROR_TYPES}"
        )

    where = "WHERE i.run_id = %s"
    params: List[Any] = [run_id]
    if error_type:
        where += (
            " AND EXISTS (SELECT 1 FROM evaluation_predictions p"
            " WHERE p.run_id = i.run_id AND p.filename = i.filename"
            " AND p.error_type = %s)"
        )
        params.append(error_type)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"SELECT COUNT(*) AS n FROM evaluation_images i {where}", tuple(params))
        total = int(cursor.fetchone()["n"])
        cursor.execute(
            f"""
            SELECT i.image_id, i.filename, i.width, i.height,
                   i.tp_count, i.fp_count, i.fn_count, i.gt_count, i.pred_count,
                   i.error_score
            FROM evaluation_images i
            {where}
            ORDER BY i.error_score DESC, i.fn_count DESC, i.filename ASC
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        )
        images = cursor.fetchall()
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return {
        "run_id": run_id,
        "error_type": error_type,
        "total": total,
        "limit": limit,
        "offset": offset,
        "images": images,
    }


@router.get("/run/{run_id}/image/{filename}")
async def get_image_detail(
    run_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    """Every box on one image, predictions and ground truth, with its diagnosis.

    What the failure explorer overlays when an image is opened.
    """
    _authorize_run(run_id, current_user)
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT image_id, filename, width, height, tp_count, fp_count,
                   fn_count, gt_count, pred_count
            FROM evaluation_images WHERE run_id = %s AND filename = %s
            """,
            (run_id, safe_filename),
        )
        summary = cursor.fetchone()
        if not summary:
            cursor.close()
            raise HTTPException(status_code=404, detail="Image not found in this run")
        cursor.execute(
            """
            SELECT outcome, error_type, pred_class, pred_class_name,
                   gt_class, gt_class_name, confidence, iou, box, gt_box
            FROM evaluation_predictions
            WHERE run_id = %s AND filename = %s
            ORDER BY FIELD(outcome, 'fn', 'fp', 'tp'), confidence DESC
            """,
            (run_id, safe_filename),
        )
        boxes = cursor.fetchall()
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass

    for box in boxes:
        for column in ("box", "gt_box"):
            value = box.get(column)
            if isinstance(value, (str, bytes)):
                try:
                    box[column] = json.loads(value)
                except (ValueError, TypeError):
                    box[column] = None

    return {"run_id": run_id, **summary, "boxes": boxes}


@router.get("/compare")
async def compare_runs(
    runs: str = Query(..., description="Comma-separated evaluation run ids"),
    current_user: dict = Depends(get_current_user),
):
    """Put runs side by side, with per-class deltas against the first.

    Only runs scored on the same version and split are really comparable, so
    the response says whether they were rather than quietly presenting
    different measurements as a ranking.
    """
    run_ids = [part.strip() for part in runs.split(",") if part.strip()]
    if len(run_ids) < 2:
        raise HTTPException(status_code=400, detail="Give at least two run ids to compare")
    if len(run_ids) > 5:
        raise HTTPException(status_code=400, detail="Compare at most five runs at a time")

    # Authorised one by one, so a comparison cannot straddle a project the
    # caller only partly has access to.
    loaded = [_authorize_run(run_id, current_user) for run_id in run_ids]
    incomplete = [run["id"] for run in loaded if run["status"] != "completed"]
    if incomplete:
        raise HTTPException(
            status_code=400, detail=f"These runs have not finished: {incomplete}"
        )

    baseline = loaded[0]
    baseline_classes = {
        entry["class_name"]: entry
        for entry in (baseline.get("per_class_metrics") or [])
    }

    comparable = len({(run["version_id"], run["split"]) for run in loaded}) == 1

    summaries = []
    for index, run in enumerate(loaded):
        metrics = {
            key: value
            for key, value in (run.get("metrics") or {}).items()
            if key != "sweep"
        }
        per_class = []
        for entry in run.get("per_class_metrics") or []:
            base = baseline_classes.get(entry["class_name"])
            per_class.append({
                **entry,
                "delta_mAP50": (
                    None if index == 0 or not base
                    else entry["mAP50"] - base["mAP50"]
                ),
            })
        summaries.append({
            "run_id": run["id"],
            "model_name": run["model_name"],
            "job_id": run["job_id"],
            "version_id": run["version_id"],
            "split": run["split"],
            "conf_threshold": run["conf_threshold"],
            "iou_threshold": run["iou_threshold"],
            "total_images": run["total_images"],
            "created_at": run["created_at"],
            "metrics": metrics,
            "per_class_metrics": per_class,
            "is_baseline": index == 0,
            "delta_map50": (
                None if index == 0
                else metrics.get("map50", 0) - (baseline.get("metrics") or {}).get("map50", 0)
            ),
        })

    best = max(summaries, key=lambda s: s["metrics"].get("map50", 0))
    return {
        "runs": summaries,
        "baseline_run_id": baseline["id"],
        "best_run_id": best["run_id"],
        # False means the runs used different versions or splits, so the
        # numbers describe different questions and ranking them is misleading.
        "comparable": comparable,
    }


def _authenticate_image_request(request: Request, token: Optional[str]) -> Dict[str, Any]:
    """Resolve the caller of an image request from a header or a query token.

    An `<img src>` cannot send an Authorization header, so the token may arrive
    in the query string. The header is preferred when both are present, since
    a URL-borne credential travels in Referer on any outbound navigation.
    """
    from app.core.rbac import decode_access_token

    bearer = request.headers.get("Authorization", "")
    header_token = bearer[7:].strip() if bearer.lower().startswith("bearer ") else None

    for candidate in (header_token, token):
        if candidate:
            payload = decode_access_token(candidate)
            if payload:
                return payload
    raise HTTPException(status_code=401, detail="Authentication required to view images")


@router.get("/image/{run_id}/{filename}")
async def serve_evaluation_image(
    run_id: str,
    filename: str,
    request: Request,
    token: Optional[str] = None,
):
    """Serve a version-snapshot image for the failure explorer.

    Accepts auth via the Authorization header or ?token=, because an <img src>
    cannot send a header — the same arrangement the annotator's image route
    uses.
    """
    payload = _authenticate_image_request(request, token)

    run = _fetch_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    dataset = DatasetService.get_dataset(run["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(run["dataset_id"], payload["user_id"], dataset["user_id"], "viewer")

    safe_filename = Path(filename).name
    if safe_filename != filename or safe_filename in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid image filename")

    # The stored path is trusted only after it is confirmed to sit inside the
    # versions tree, so a tampered row cannot turn this into a file reader.
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT path FROM evaluation_images WHERE run_id = %s AND filename = %s",
            (run_id, safe_filename),
        )
        row = cursor.fetchone()
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass

    if not row or not row.get("path"):
        raise HTTPException(status_code=404, detail="Image not found in this run")

    image_path = Path(row["path"]).resolve()
    if not str(image_path).startswith(str(_VERSIONS_BASE)):
        logger.error(f"evaluation: refusing to serve {image_path} — outside {_VERSIONS_BASE}")
        raise HTTPException(status_code=400, detail="Invalid image path")
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {safe_filename}")

    return FileResponse(
        path=str(image_path),
        media_type="image/jpeg",
        headers={
            # Snapshot images are immutable, but they are also per-project, so
            # only the viewer's own browser may keep a copy.
            "Cache-Control": "private, max-age=3600",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.delete("/run/{run_id}")
async def delete_evaluation_run(run_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a run. Its images and per-box rows cascade."""
    _authorize_run(run_id, current_user, minimum="annotator")
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM evaluation_runs WHERE id = %s", (run_id,))
        connection.commit()
        cursor.close()
    finally:
        try:
            connection.close()
        except Exception:
            pass
    return {"status": "deleted", "run_id": run_id}
