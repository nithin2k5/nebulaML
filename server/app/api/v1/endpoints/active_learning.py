"""
Active Learning Endpoint

Collects low-confidence predictions from deployed models,
flags uncertain images for human review, and supports re-training loops.
"""

from fastapi import APIRouter, HTTPException, Form, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import logging
from pathlib import Path

from app.services.database import DatasetService, AnnotationService
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store for uncertain predictions (would be DB-backed in production)
uncertain_predictions: Dict[str, List[Dict]] = {}


class CollectRequest(BaseModel):
    dataset_id: str
    model_job_id: str
    confidence_threshold: float = 0.5
    max_images: int = 50


class ApproveRequest(BaseModel):
    dataset_id: str
    predictions: List[Dict[str, Any]]


@router.post("/collect")
async def collect_uncertain(
    request: CollectRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Run inference on dataset images and collect predictions with confidence
    below the threshold. These are flagged for human review.
    """
    from app.services.inference import YOLOInference
    from PIL import Image as PILImage

    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Determine model path
    weights_dir = Path("runs/detect") / f"job_{request.model_job_id}" / "weights"
    onnx_path = weights_dir / "best.onnx"
    pt_path = weights_dir / "best.pt"

    if onnx_path.exists():
        model_path = str(onnx_path)
    elif pt_path.exists():
        model_path = str(pt_path)
    else:
        raise HTTPException(status_code=404, detail=f"Model for job {request.model_job_id} not found")

    # Load model
    inference = YOLOInference(model_path)

    # Get all images from dataset
    images = DatasetService.get_dataset_images(request.dataset_id)

    uncertain = []
    for img_data in images[:request.max_images * 3]:  # Check more images than needed
        if len(uncertain) >= request.max_images:
            break

        img_path = Path(img_data.get("path", ""))
        if not img_path.exists():
            continue

        try:
            pil_img = PILImage.open(str(img_path))
            detections = inference.predict(pil_img, conf_threshold=0.01)

            # Find low-confidence detections
            low_conf = [d for d in detections if d.get("confidence", 1.0) < request.confidence_threshold]
            high_conf = [d for d in detections if d.get("confidence", 1.0) >= request.confidence_threshold]

            if low_conf or (not detections):
                uncertain.append({
                    "image_id": img_data["id"],
                    "filename": img_data.get("filename", ""),
                    "path": img_data.get("path", ""),
                    "low_confidence_detections": low_conf,
                    "high_confidence_detections": high_conf,
                    "total_detections": len(detections),
                    "min_confidence": min((d.get("confidence", 0) for d in detections), default=0),
                    "needs_review": True
                })
        except Exception as e:
            logger.warning(f"Failed to process image {img_data.get('filename')}: {e}")

    # Store results
    uncertain_predictions[request.dataset_id] = uncertain

    return JSONResponse(content={
        "success": True,
        "dataset_id": request.dataset_id,
        "model_job_id": request.model_job_id,
        "confidence_threshold": request.confidence_threshold,
        "images_scanned": min(len(images), request.max_images * 3),
        "uncertain_count": len(uncertain),
        "uncertain_images": uncertain[:20]  # Return first 20 in response
    })


@router.get("/uncertain/{dataset_id}")
async def get_uncertain_images(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    List images with uncertain/low-confidence predictions that need human review.
    """
    images = uncertain_predictions.get(dataset_id, [])
    return {
        "dataset_id": dataset_id,
        "total_uncertain": len(images),
        "images": images
    }


@router.post("/approve")
async def approve_predictions(
    request: ApproveRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Approve uncertain predictions and save them as annotations.
    This adds the reviewed predictions to the training dataset.
    """
    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    approved_count = 0
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
                status="annotated"
            )
            approved_count += 1
        except Exception as e:
            logger.warning(f"Failed to approve prediction for image {image_id}: {e}")

    # Remove approved images from uncertain list
    if request.dataset_id in uncertain_predictions:
        approved_ids = {p.get("image_id") for p in request.predictions}
        uncertain_predictions[request.dataset_id] = [
            img for img in uncertain_predictions[request.dataset_id]
            if img["image_id"] not in approved_ids
        ]

    return {
        "success": True,
        "approved_count": approved_count,
        "remaining_uncertain": len(uncertain_predictions.get(request.dataset_id, []))
    }


@router.delete("/clear/{dataset_id}")
async def clear_uncertain(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Clear all uncertain predictions for a dataset."""
    uncertain_predictions.pop(dataset_id, None)
    return {"success": True, "message": "Cleared uncertain predictions"}
