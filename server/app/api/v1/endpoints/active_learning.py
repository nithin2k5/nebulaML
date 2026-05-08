"""
Active Learning Endpoint

Collects low-confidence predictions from deployed models,
flags uncertain images for human review, and supports re-training loops.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import json
import logging
from pathlib import Path

from app.db.session import get_db_connection
from app.services.database import DatasetService, AnnotationService
from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[4]
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

active_learning_jobs: Dict[str, Dict] = {}


class CollectRequest(BaseModel):
    dataset_id: str
    model_job_id: str
    confidence_threshold: float = 0.5
    max_images: int = 50


class ApproveRequest(BaseModel):
    dataset_id: str
    predictions: List[Dict[str, Any]]


class RejectRequest(BaseModel):
    dataset_id: str
    image_ids: List[str]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _save_uncertain_batch(dataset_id: str, images: List[Dict]) -> None:
    """Upsert uncertain images for a dataset (replaces previous batch)."""
    connection = get_db_connection()
    if not connection:
        return
    try:
        cursor = connection.cursor()
        # Clear existing for this dataset first (full rescan replaces old results)
        cursor.execute("DELETE FROM uncertain_images WHERE dataset_id = %s", (dataset_id,))
        for img in images:
            cursor.execute(
                """INSERT INTO uncertain_images
                   (dataset_id, image_id, filename, low_confidence_detections,
                    high_confidence_detections, total_detections, min_confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       low_confidence_detections = VALUES(low_confidence_detections),
                       high_confidence_detections = VALUES(high_confidence_detections),
                       total_detections = VALUES(total_detections),
                       min_confidence = VALUES(min_confidence)""",
                (
                    dataset_id,
                    img["image_id"],
                    img["filename"],
                    json.dumps(img.get("low_confidence_detections", [])),
                    json.dumps(img.get("high_confidence_detections", [])),
                    img.get("total_detections", 0),
                    img.get("min_confidence", 0),
                ),
            )
        connection.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Failed to save uncertain batch: {e}")
    finally:
        connection.close()


def _load_uncertain_images(dataset_id: str) -> List[Dict]:
    connection = get_db_connection()
    if not connection:
        return []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT image_id, filename, low_confidence_detections,
                      high_confidence_detections, total_detections, min_confidence
               FROM uncertain_images
               WHERE dataset_id = %s
               ORDER BY min_confidence ASC""",
            (dataset_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        for row in rows:
            row["low_confidence_detections"] = json.loads(row["low_confidence_detections"] or "[]")
            row["high_confidence_detections"] = json.loads(row["high_confidence_detections"] or "[]")
            row["needs_review"] = True
        return rows
    except Exception as e:
        logger.error(f"Failed to load uncertain images: {e}")
        return []
    finally:
        connection.close()


def _remove_uncertain_images(dataset_id: str, image_ids: set) -> None:
    if not image_ids:
        return
    connection = get_db_connection()
    if not connection:
        return
    try:
        cursor = connection.cursor()
        placeholders = ",".join(["%s"] * len(image_ids))
        cursor.execute(
            f"DELETE FROM uncertain_images WHERE dataset_id = %s AND image_id IN ({placeholders})",
            (dataset_id, *image_ids),
        )
        connection.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Failed to remove uncertain images: {e}")
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _collect_task(dataset_id: str, model_job_id: str, confidence_threshold: float, max_images: int):
    try:
        from app.services.inference import YOLOInference
        from PIL import Image as PILImage
        
        # Determine model path
        weights_dir = (_RUNS_BASE / f"job_{model_job_id}" / "weights").resolve()
        onnx_path = weights_dir / "best.onnx"
        pt_path = weights_dir / "best.pt"

        if onnx_path.exists():
            model_path = str(onnx_path)
        elif pt_path.exists():
            model_path = str(pt_path)
        else:
            raise Exception("Model not found")

        inference = YOLOInference(model_path)
        images = DatasetService.get_dataset_images(dataset_id)

        uncertain = []
        for img_data in images[: max_images * 3]:
            if len(uncertain) >= max_images:
                break

            img_path = Path(img_data.get("path", ""))
            if not img_path.exists():
                continue

            try:
                pil_img = PILImage.open(str(img_path))
                detections = inference.predict(pil_img, conf_threshold=0.01)

                low_conf = [d for d in detections if d.get("confidence", 1.0) < confidence_threshold]
                high_conf = [d for d in detections if d.get("confidence", 1.0) >= confidence_threshold]

                if low_conf or (not detections):
                    uncertain.append({
                        "image_id": img_data["id"],
                        "filename": img_data.get("filename", ""),
                        "path": img_data.get("path", ""),
                        "low_confidence_detections": low_conf,
                        "high_confidence_detections": high_conf,
                        "total_detections": len(detections),
                        "min_confidence": min((d.get("confidence", 0) for d in detections), default=0),
                        "needs_review": True,
                    })
            except Exception as e:
                logger.warning(f"Failed to process image {img_data.get('filename')}: {e}")

        _save_uncertain_batch(dataset_id, uncertain)
        
        active_learning_jobs[dataset_id] = {
            "status": "completed",
            "uncertain_count": len(uncertain)
        }
    except Exception as e:
        logger.error(f"Active learning collection failed: {e}")
        active_learning_jobs[dataset_id] = {
            "status": "failed",
            "error": str(e)
        }


@router.post("/collect")
async def collect_uncertain(
    request: CollectRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Run inference on dataset images and collect predictions with confidence
    below the threshold. These are flagged for human review.
    """
    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(request.dataset_id, current_user["id"], dataset["user_id"], "annotator")

    weights_dir = (_RUNS_BASE / f"job_{request.model_job_id}" / "weights").resolve()
    if not str(weights_dir).startswith(str(_RUNS_BASE)):
        raise HTTPException(status_code=400, detail="Invalid job ID")

    active_learning_jobs[request.dataset_id] = {
        "status": "processing"
    }

    background_tasks.add_task(
        _collect_task,
        request.dataset_id,
        request.model_job_id,
        request.confidence_threshold,
        request.max_images
    )

    return JSONResponse(content={
        "status": "processing",
        "message": "Scanning dataset in background"
    })

@router.get("/collect-status/{dataset_id}")
async def get_collect_status(dataset_id: str, current_user: dict = Depends(get_current_user)):
    if dataset_id not in active_learning_jobs:
        # Default to completed if no job exists to prevent infinite polling
        return {"status": "completed", "uncertain_count": 0}
    return active_learning_jobs[dataset_id]


@router.get("/uncertain/{dataset_id}")
async def get_uncertain_images(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List images with uncertain/low-confidence predictions that need human review."""
    from app.services.database import DatasetService as DS
    dataset = DS.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")
    images = _load_uncertain_images(dataset_id)
    return {
        "dataset_id": dataset_id,
        "total_uncertain": len(images),
        "images": images,
    }


@router.post("/approve")
async def approve_predictions(
    request: ApproveRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Approve uncertain predictions and save them as annotations.
    This adds the reviewed predictions to the training dataset.
    """
    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(request.dataset_id, current_user["id"], dataset["user_id"], "annotator")

    approved_count = 0
    approved_ids = set()

    for pred in request.predictions:
        image_id = pred.get("image_id")
        boxes = pred.get("boxes", [])

        if not image_id or not boxes:
            continue

        try:
            annotation_id = str(uuid.uuid4())[:8]
            AnnotationService.save_annotation(
                annotation_id=annotation_id,
                dataset_id=request.dataset_id,
                image_id=image_id,
                image_name=pred.get("filename", ""),
                width=pred.get("width", 640),
                height=pred.get("height", 640),
                boxes=boxes,
                split="train",
                status="annotated",
            )
            approved_ids.add(image_id)
            approved_count += 1
        except Exception as e:
            logger.warning(f"Failed to approve prediction for image {image_id}: {e}")

    _remove_uncertain_images(request.dataset_id, approved_ids)

    remaining = _load_uncertain_images(request.dataset_id)
    return {
        "success": True,
        "approved_count": approved_count,
        "remaining_uncertain": len(remaining),
    }


@router.post("/reject")
async def reject_predictions(
    request: RejectRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Reject (discard) uncertain images without adding them to training data.
    Removes the selected image_ids from the uncertain_images queue.
    """
    from app.services.database import DatasetService as DS
    dataset = DS.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(request.dataset_id, current_user["id"], dataset["user_id"], "annotator")
    _remove_uncertain_images(request.dataset_id, set(request.image_ids))
    remaining = _load_uncertain_images(request.dataset_id)
    return {
        "success": True,
        "rejected_count": len(request.image_ids),
        "remaining_uncertain": len(remaining),
    }


@router.delete("/clear/{dataset_id}")
async def clear_uncertain(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Clear all uncertain predictions for a dataset."""
    _save_uncertain_batch(dataset_id, [])
    return {"success": True, "message": "Cleared uncertain predictions"}
