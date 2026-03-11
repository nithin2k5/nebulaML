from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
import io
from pathlib import Path
from PIL import Image
from functools import lru_cache

from app.services.inference import YOLOInference

router = APIRouter()

@lru_cache(maxsize=3)
def get_inference_model(model_path: str) -> YOLOInference:
    """Load and cache up to 3 models in memory for fast swapping"""
    return YOLOInference(model_path)

@router.post("/predict")
async def predict_image(
    file: UploadFile = File(...),
    confidence: Optional[float] = Form(0.25),
    model_name: Optional[str] = Form("yolov8n.pt"),
    job_id: Optional[str] = Form(None),
    agnostic_nms: Optional[bool] = Form(False),
    augment: Optional[bool] = Form(False)
):
    """
    Run inference on uploaded image. 
    If job_id is provided, loads trained weights from that job. 
    Otherwise uses pretrained model_name.
    """
    global inference_model
    
    try:
        # Determine model path
        model_path = model_name
        
        if job_id:
            weights_dir = Path("runs/detect") / f"job_{job_id}" / "weights"
            onnx_path = weights_dir / "best.onnx"
            pt_path = weights_dir / "best.pt"
            
            if onnx_path.exists():
                model_path = str(onnx_path)
            elif pt_path.exists():
                model_path = str(pt_path)
            else:
                raise HTTPException(status_code=404, detail=f"Trained model for job {job_id} not found at {weights_dir}")
                
        # Get cached model
        inference_model = get_inference_model(model_path)

        
        # Process image in memory
        content = await file.read()
        image = Image.open(io.BytesIO(content))
        
        # Run inference
        detections = inference_model.predict(
            image, 
            conf_threshold=confidence,
            agnostic_nms=agnostic_nms,
            augment=augment
        )
        
        return JSONResponse(content={
            "success": True,
            "detections": detections,
            "image_name": file.filename,
            "num_detections": len(detections)
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predict-batch")
async def predict_batch(
    files: List[UploadFile] = File(...),
    confidence: Optional[float] = Form(0.25),
    agnostic_nms: Optional[bool] = Form(False),
    augment: Optional[bool] = Form(False)
):
    """
    Run inference on multiple images
    """
    try:
        # We need a model_name or job_id to know which model to use.
        # But this endpoint doesn't accept model_name easily in the signature. Default to base.
        inference_model = get_inference_model("yolov8n.pt")
        
        all_results = []
        images = []
        
        # Read all files into memory
        for file in files:
            content = await file.read()
            images.append(Image.open(io.BytesIO(content)))
        
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models")
async def list_available_models():
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

