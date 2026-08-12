from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends, Request
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
import io
from pathlib import Path
from PIL import Image
from functools import lru_cache
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.inference import YOLOInference
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Resolve the runs directory relative to this file's location so it is always
# consistent regardless of the working directory uvicorn is launched from.
_SERVER_ROOT = Path(__file__).resolve().parents[4]  # …/server/
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

# Max image upload size for inference: 10 MB
_MAX_INFERENCE_SIZE = 10 * 1024 * 1024


@lru_cache(maxsize=3)
def get_inference_model(model_path: str, model_type: str = "yolo"):
    """Load and cache up to 3 models in memory for fast swapping"""
    from app.services.trainer_factory import create_inference
    return create_inference(model_path, model_type)


import logging
logger = logging.getLogger(__name__)

def _get_job_model_type(job_id: str) -> str:
    """Get the model backend type for a training job."""
    from app.api.v1.endpoints.training import training_jobs, _ensure_jobs_loaded
    _ensure_jobs_loaded()
    job = training_jobs.get(job_id, {})
    model_type = job.get("model_type", "yolo")
    return model_type

def _resolve_job_weights(job_id: str) -> str:
    """Return the absolute path to the best weights for a training job.

    Raises HTTPException 400 if job_id looks malicious, 404 if weights are missing.
    """
    logger.error(f"DEBUG_RESOLVE: job_id received: {job_id}")
    
    # Reject obvious path-traversal attempts
    if ".." in job_id or "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    weights_dir = (_RUNS_BASE / f"job_{job_id}" / "weights").resolve()
    
    # Verify the resolved path is still inside the expected subtree
    if not str(weights_dir).startswith(str(_RUNS_BASE)):
        raise HTTPException(status_code=400, detail="Invalid job_id")

    onnx_path = weights_dir / "best.onnx"
    pt_path = weights_dir / "best.pt"
    meta_path = weights_dir.parent / "model_meta.json"
    
    with open("/tmp/inference_debug.log", "a") as f:
        f.write(f"RESOLVE: job_id={job_id}, weights_dir={weights_dir}, pt={pt_path.exists()}, onnx={onnx_path.exists()}, meta={meta_path.exists()}\n")

    if onnx_path.exists():
        return str(onnx_path)
    if pt_path.exists():
        return str(pt_path)
    if meta_path.exists():
        return str(meta_path)

    raise HTTPException(
        status_code=404,
        detail=f"Trained model weights not found for this job. Ensure training completed successfully (expected: {weights_dir})"
    )


@router.post("/predict")
@limiter.limit("30/minute")
async def predict_image(
    request: Request,
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
        # Determine model path and type
        if job_id:
            model_path = _resolve_job_weights(job_id)
            model_type = _get_job_model_type(job_id)
        else:
            from app.services.model_registry import get_backend
            model_path = model_name or "yolov8n.pt"
            model_type = get_backend(model_path)

        # Get cached model
        inference_model = get_inference_model(model_path, model_type)

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
        
    except HTTPException as e:
        with open("/tmp/inference_debug.log", "a") as f:
            f.write(f"HTTP Exception in predict: {e.status_code} {e.detail}\n")
        raise
    except Exception as e:
        with open("/tmp/inference_debug.log", "a") as f:
            f.write(f"Generic Exception in predict: {str(e)}\n")
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
        # Resolve model path and type (same logic as /predict)
        if job_id:
            model_path = _resolve_job_weights(job_id)
            model_type = _get_job_model_type(job_id)
        else:
            from app.services.model_registry import get_backend
            model_path = model_name or "yolov8n.pt"
            model_type = get_backend(model_path)
            
        inference_model = get_inference_model(model_path, model_type)
        
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
    List available models from the registry
    """
    from app.services.model_registry import get_registry_for_api
    return {"models": get_registry_for_api()}

