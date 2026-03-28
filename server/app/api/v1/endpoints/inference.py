from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
import io
from pathlib import Path
from PIL import Image
from functools import lru_cache

from app.services.inference import YOLOInference
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

# Resolve the runs directory relative to this file's location so it is always
# consistent regardless of the working directory uvicorn is launched from.
_SERVER_ROOT = Path(__file__).resolve().parents[4]  # …/server/
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

# Max image upload size for inference: 10 MB
_MAX_INFERENCE_SIZE = 10 * 1024 * 1024


@lru_cache(maxsize=3)
def get_inference_model(model_path: str) -> YOLOInference:
    """Load and cache up to 3 models in memory for fast swapping"""
    return YOLOInference(model_path)


def _resolve_job_weights(job_id: str) -> str:
    """Return the absolute path to the best weights for a training job.

    Raises HTTPException 400 if job_id looks malicious, 404 if weights are missing.
    """
    # Reject obvious path-traversal attempts
    if ".." in job_id or "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    weights_dir = (_RUNS_BASE / f"job_{job_id}" / "weights").resolve()

    # Verify the resolved path is still inside the expected subtree
    if not str(weights_dir).startswith(str(_RUNS_BASE)):
        raise HTTPException(status_code=400, detail="Invalid job_id")

    onnx_path = weights_dir / "best.onnx"
    pt_path = weights_dir / "best.pt"

    if onnx_path.exists():
        return str(onnx_path)
    if pt_path.exists():
        return str(pt_path)

    raise HTTPException(
        status_code=404,
        detail=f"Trained model weights not found for this job. Ensure training completed successfully (expected: {weights_dir})"
    )


@router.post("/predict")
async def predict_image(
    file: UploadFile = File(...),
    confidence: Optional[float] = Form(0.25),
    iou: Optional[float] = Form(0.45),
    model_name: Optional[str] = Form("yolov8n.pt"),
    job_id: Optional[str] = Form(None),
    agnostic_nms: Optional[bool] = Form(False),
    augment: Optional[bool] = Form(False),
    current_user: dict = Depends(get_current_user)
):
    """
    Run inference on uploaded image. Requires authentication.
    If job_id is provided, loads trained weights from that job.
    Otherwise uses pretrained model_name.
    """
    try:
        # Determine model path
        model_path = _resolve_job_weights(job_id) if job_id else (model_name or "yolov8n.pt")

        # Get cached model
        inference_model = get_inference_model(model_path)

        # Enforce file size limit
        content = await file.read()
        if len(content) > _MAX_INFERENCE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {_MAX_INFERENCE_SIZE // 1024 // 1024} MB)")

        # Validate it's a real image
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
            image = Image.open(io.BytesIO(content))  # re-open after verify
        except Exception:
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")
        
        # Run inference
        detections = inference_model.predict(
            image, 
            conf_threshold=confidence,
            iou_threshold=iou,
            agnostic_nms=agnostic_nms,
            augment=augment
        )
        
        return JSONResponse(content={
            "success": True,
            "detections": detections,
            "image_name": file.filename,
            "num_detections": len(detections)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict-batch")
async def predict_batch(
    files: List[UploadFile] = File(...),
    confidence: Optional[float] = Form(0.25),
    agnostic_nms: Optional[bool] = Form(False),
    augment: Optional[bool] = Form(False),
    model_name: Optional[str] = Form("yolov8n.pt"),
    job_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Run inference on multiple images. Requires authentication.
    """
    # Limit batch size to 20 images
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Batch inference is limited to 20 images at a time")

    try:
        # Resolve model path (same logic as /predict)
        model_path = _resolve_job_weights(job_id) if job_id else (model_name or "yolov8n.pt")
        inference_model = get_inference_model(model_path)
        
        all_results = []
        images = []
        
        # Read all files into memory
        for file in files:
            content = await file.read()
            if len(content) > _MAX_INFERENCE_SIZE:
                raise HTTPException(status_code=413, detail=f"{file.filename}: File too large (max {_MAX_INFERENCE_SIZE // 1024 // 1024} MB)")
            try:
                images.append(Image.open(io.BytesIO(content)))
            except Exception:
                raise HTTPException(status_code=400, detail=f"{file.filename}: Not a valid image")
        
        # Run batch inference
        all_detections = inference_model.predict_batch(
            images,
            conf_threshold=confidence,
            agnostic_nms=agnostic_nms,
            augment=augment
        )
        
        # Format results
        for file, detections in zip(files, all_detections):
            all_results.append({
                "image_name": file.filename,
                "detections": detections,
                "num_detections": len(detections)
            })
        
        return JSONResponse(content={
            "success": True,
            "results": all_results,
            "total_images": len(files)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_available_models(current_user: dict = Depends(get_current_user)):
    """
    List available YOLO models
    """
    return {
        "models": [
            {"name": "yolov8n.pt", "size": "Nano", "description": "Fastest, lowest accuracy"},
            {"name": "yolov8s.pt", "size": "Small", "description": "Balanced speed and accuracy"},
            {"name": "yolov8m.pt", "size": "Medium", "description": "Good accuracy"},
            {"name": "yolov8l.pt", "size": "Large", "description": "High accuracy"},
            {"name": "yolov8x.pt", "size": "Extra Large", "description": "Highest accuracy, slowest"},
            {"name": "yolov9t.pt", "size": "Tiny", "description": "YOLOv9 Tiny - fast and accurate"},
            {"name": "yolov9s.pt", "size": "Small", "description": "YOLOv9 Small - balanced"},
            {"name": "yolov9c.pt", "size": "Compact", "description": "YOLOv9 Compact"},
            {"name": "yolov9e.pt", "size": "Extra Large", "description": "YOLOv9 Extended"},
            {"name": "yolov10n.pt", "size": "Nano", "description": "YOLOv10 Nano"},
            {"name": "yolov10s.pt", "size": "Small", "description": "YOLOv10 Small"},
            {"name": "yolov10x.pt", "size": "Extra Large", "description": "YOLOv10 Extra Large"},
            {"name": "yolo11n.pt", "size": "Nano", "description": "YOLO11 Nano - latest SOTA"},
            {"name": "yolo11s.pt", "size": "Small", "description": "YOLO11 Small"},
            {"name": "yolo11m.pt", "size": "Medium", "description": "YOLO11 Medium"},
            {"name": "yolo11x.pt", "size": "Extra Large", "description": "YOLO11 Extra Large SOTA"},
        ]
    }

