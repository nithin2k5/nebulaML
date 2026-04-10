from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Form, Depends
from typing import Optional
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import json
import os
import yaml
from pathlib import Path
import tempfile
import uuid
import logging
import sys

import shutil

# Import trainer
from app.services.trainer import YOLOTrainer
from app.services.dataset_analyzer import DatasetAnalyzer
from app.services.database import DatasetService, DatasetVersionService, TrainingJobService
from app.services.versioning import VersioningEngine
from app.api.v1.endpoints.auth import get_current_user
from utils.dataset_utils import split_dataset_stratified

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_CONCURRENT_JOBS = 2

training_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_loaded = False

def _ensure_jobs_loaded():
    global _jobs_loaded
    if not _jobs_loaded:
        try:
            persisted = TrainingJobService.load_all_jobs()
            training_jobs.update(persisted)
            _jobs_loaded = True
            logger.info(f"Loaded {len(persisted)} training jobs from DB")
        except Exception as e:
            logger.warning(f"Could not load jobs from DB: {e}")
            _jobs_loaded = True

def _persist_job(job_id: str):
    try:
        TrainingJobService.upsert_job(job_id, training_jobs[job_id])
    except Exception as e:
        logger.warning(f"Could not persist job {job_id}: {e}")


def _job_owner_ok(job: Dict[str, Any], current_user: dict) -> bool:
    uid = job.get("user_id")
    if uid is None:
        return True
    return uid == current_user.get("id")

ALLOWED_MODELS = {
    # YOLOv8
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
    # YOLOv9
    "yolov9t.pt", "yolov9s.pt", "yolov9c.pt", "yolov9e.pt",
    # YOLOv10
    "yolov10n.pt", "yolov10s.pt", "yolov10m.pt", "yolov10l.pt", "yolov10x.pt",
    # YOLO11
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
}

class TrainingConfig(BaseModel):
    epochs: int = Field(default=100, ge=1, le=1000, description="Number of training epochs (1-1000)")
    batch_size: int = Field(default=16, ge=1, le=128, description="Batch size (1-128)")
    img_size: int = Field(default=640, ge=320, le=1280, description="Image size (320-1280)")
    model_name: str = Field(default="yolov8n.pt", description="Base model name (yolov8, yolov9, yolov10, yolo11)")
    learning_rate: Optional[float] = Field(default=None, ge=0.0001, le=1.0, description="Learning rate")
    patience: Optional[int] = Field(default=50, ge=1, le=200, description="Early stopping patience")
    device: Optional[str] = Field(default=None, description="Device (cpu, cuda, mps, or None for auto)")
    strict_epochs: bool = Field(default=False, description="If True, enforce exact epoch count (disable early stopping)")
    augmentations: Optional[Dict[str, Any]] = Field(default=None, description="Data augmentation parameters")
    preset: Optional[str] = Field(default=None, description="Preset name: fast, balanced, accurate")

    @validator('model_name')
    def validate_model_name(cls, v):
        if v not in ALLOWED_MODELS:
            raise ValueError(f"Unsupported model '{v}'. Allowed: {sorted(ALLOWED_MODELS)}")
        return v

    def apply_preset(self):
        """Apply a named preset, overriding defaults but not user-set values."""
        presets = {
            "fast": {"epochs": 25, "batch_size": 32, "img_size": 416, "model_name": "yolov8n.pt", "patience": 10, "learning_rate": 0.01},
            "balanced": {"epochs": 100, "batch_size": 16, "img_size": 640, "model_name": "yolov8s.pt", "patience": 50, "learning_rate": 0.01},
            "accurate": {"epochs": 300, "batch_size": 8, "img_size": 1024, "model_name": "yolov8m.pt", "patience": 80, "learning_rate": 0.001},
        }
        if self.preset and self.preset in presets:
            p = presets[self.preset]
            for k, v in p.items():
                setattr(self, k, v)
        return self
    
    @validator('epochs')
    def validate_epochs(cls, v):
        if v < 1:
            raise ValueError("Epochs must be at least 1")
        if v > 1000:
            raise ValueError("Epochs cannot exceed 1000")
        return v
    
    @validator('batch_size')
    def validate_batch_size(cls, v):
        if v < 1:
            raise ValueError("Batch size must be at least 1")
        if v > 128:
            raise ValueError("Batch size cannot exceed 128")
        return v

class DatasetTrainingRequest(BaseModel):
    dataset_id: str
    version_id: str
    config: TrainingConfig
    classes: Optional[List[str]] = None  # Optional list of class names to filter
    
class ExportAndTrainRequest(BaseModel):
    dataset_id: str
    config: TrainingConfig

class GenerateVersionRequest(BaseModel):
    dataset_id: str
    name: str = "Version 1"
    preprocessing: Dict[str, Any] = {}
    augmentations: Dict[str, Any] = {}

class AutoRetrainConfig(BaseModel):
    dataset_id: str
    enabled: bool = False
    min_new_annotations: int = Field(default=50, ge=10, le=1000)

# In-memory store for auto-retrain configs
auto_retrain_configs: Dict[str, Dict[str, Any]] = {}
    
@router.post("/versions/generate")
async def generate_dataset_version(
    request: GenerateVersionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an immutable Roboflow-style version of a dataset 
    with specific preprocessing and augmentations.
    Requires authentication.
    """
    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    from app.core.access import require_role
    require_role(request.dataset_id, current_user["id"], dataset["user_id"], "admin")

    engine = VersioningEngine()
    version_id = engine.generate_version(
        dataset_id=request.dataset_id,
        name=request.name,
        preprocessing=request.preprocessing,
        augmentations=request.augmentations
    )
    
    if not version_id:
        raise HTTPException(status_code=500, detail="Failed to generate dataset version")
        
    return {
        "success": True,
        "version_id": version_id,
        "message": "Dataset version successfully generated."
    }

@router.get("/versions/list/{dataset_id}")
async def list_dataset_versions(dataset_id: str, current_user: dict = Depends(get_current_user)):
    """
    List all generated versions of a dataset
    """
    versions = DatasetVersionService.list_dataset_versions(dataset_id)
    return {"versions": versions}

@router.post("/start")
async def start_training(
    background_tasks: BackgroundTasks,
    dataset_yaml: UploadFile = File(...),
    epochs: int = Form(100),
    batch_size: int = Form(16),
    img_size: int = Form(640),
    model_name: str = Form("yolov8n.pt"),
    learning_rate: Optional[float] = Form(None),
    patience: Optional[int] = Form(50),
    device: Optional[str] = Form(None),
    strict_epochs: bool = Form(False),
    current_user: dict = Depends(get_current_user)
):
    """
    Start model training job. Requires authentication.
    """
    _ensure_jobs_loaded()
    # Validate YAML content-type
    if dataset_yaml.content_type and not (
        dataset_yaml.content_type in ["application/x-yaml", "text/yaml", "text/plain", "application/octet-stream"]
    ):
        raise HTTPException(status_code=400, detail="Uploaded file must be a YAML file")

    # Enforce concurrency limit
    active = sum(1 for j in training_jobs.values() if j.get("status") == "running")
    if active >= MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many training jobs running ({active}/{MAX_CONCURRENT_JOBS}). Wait for one to finish before starting another."
        )

    try:
        # Create TrainingConfig from form data
        config = TrainingConfig(
            epochs=epochs,
            batch_size=batch_size,
            img_size=img_size,
            model_name=model_name,
            learning_rate=learning_rate,
            patience=patience,
            device=device,
            strict_epochs=strict_epochs
        )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Save dataset config
        temp_dir = Path(tempfile.gettempdir()) / "yolo_training" / job_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        yaml_path = temp_dir / "data.yaml"
        with open(yaml_path, 'wb') as f:
            content = await dataset_yaml.read()
            f.write(content)
        
        # Register job
        training_jobs[job_id] = {
            "status": "pending",
            "config": config.dict(),
            "output": [],
            "metrics": {},
            "progress": 0,
            "dataset_id": None,
            "created_at": datetime.now().isoformat(),
            "user_id": current_user["id"],
            "cancel_requested": False,
        }
        _persist_job(job_id)

        background_tasks.add_task(run_training, job_id, str(yaml_path), config)
        
        return {"job_id": job_id, "status": "started"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start training: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start-micro")
async def start_micro_training(
    background_tasks: BackgroundTasks,
    dataset_id: str = Form(...),
    model_name: str = Form("yolov8n.pt"),
    epochs: int = Form(10),
    batch_size: int = Form(16),
    img_size: int = Form(416),
    device: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Start a 'Micro-Training' job for quick iteration.
    Uses existing dataset from database instead of uploaded YAML.
    """
    _ensure_jobs_loaded()
    try:
        # Create minimal config
        config = TrainingConfig(
            epochs=epochs,
            batch_size=batch_size,
            img_size=img_size,
            model_name=model_name,
            device=device,
            patience=5, # Short patience
            strict_epochs=False
        )
        
        job_id = str(uuid.uuid4())
        
        yaml_path = Path(f"datasets/{dataset_id}/data.yaml")
        if not yaml_path.exists():
            raise HTTPException(status_code=400, detail="Dataset not exported yet. Please export the dataset before micro-training.")
            
        # Fetch recommendations to improve micro-training accuracy
        try:
            analysis = DatasetAnalyzer.analyze_dataset(dataset_id)
            recs = analysis.augmentation_recommendations
            # Override defaults with recommendations if it's a micro-job
            config.img_size = analysis.recommended_image_size
            config.augmentations = recs
            logger.info(f"Applied analyzer recommendations for job {job_id}: imgsz={config.img_size}")
        except Exception as e:
            logger.warning(f"Could not fetch recommendations: {e}")

        training_jobs[job_id] = {
            "status": "pending",
            "config": config.dict(),
            "output": [f"Starting micro-training on dataset {dataset_id}..."],
            "metrics": {},
            "progress": 0,
            "dataset_id": dataset_id,
            "created_at": datetime.now().isoformat(),
            "user_id": current_user["id"],
            "cancel_requested": False,
        }
        _persist_job(job_id)

        background_tasks.add_task(run_training, job_id, str(yaml_path), config)
        
        return {"job_id": job_id, "status": "started"}

    except Exception as e:
        logger.error(f"Failed to start micro-training: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_training(job_id: str, data_yaml: str, config: TrainingConfig):
    """
    Background task to run training with strict validation
    """
    try:
        training_jobs[job_id]["status"] = "running"
        training_jobs[job_id]["progress"] = 0
        training_jobs[job_id]["current_epoch"] = 0
        training_jobs[job_id]["cancel_requested"] = training_jobs[job_id].get("cancel_requested", False)
        _persist_job(job_id)

        if training_jobs[job_id].get("cancel_requested"):
            training_jobs[job_id].update({
                "status": "cancelled",
                "cancelled_at": datetime.now().isoformat(),
            })
            _persist_job(job_id)
            logger.info(f"Training job {job_id} cancelled before start")
            return
        
        logger.info(f"Starting training job {job_id} with {config.epochs} epochs")
        
        # Validate dataset YAML exists
        if not Path(data_yaml).exists():
            raise FileNotFoundError(f"Dataset YAML not found: {data_yaml}")
        
        # Initialize trainer
        trainer = YOLOTrainer(config.model_name)
        
        # Training parameters with strict configuration
        train_params = {
            "data_yaml": data_yaml,
            "epochs": config.epochs,
            "imgsz": config.img_size,
            "batch": config.batch_size,
            "name": f"job_{job_id}",
            "project": "runs/detect",
            "exist_ok": True,
            "strict_epochs": config.strict_epochs,  # Pass strict mode to trainer
        }
        
        # Add optional parameters
        if config.learning_rate:
            train_params["lr0"] = config.learning_rate
        if config.patience and not config.strict_epochs:
            # Only use patience if not in strict mode
            train_params["patience"] = config.patience
        elif config.strict_epochs:
            # In strict mode, disable early stopping - ensure all epochs run
            train_params["patience"] = config.epochs + 1
            train_params["save_period"] = 10  # Save checkpoints every 10 epochs
        if config.device:
            train_params["device"] = config.device
        
        # Add augmentations if present
        if config.augmentations:
            train_params["augmentations"] = config.augmentations
            
        def epoch_end_callback(trainer_obj):
            try:
                epoch = trainer_obj.epoch + 1
                total_epochs = trainer_obj.epochs
                progress = (epoch / total_epochs) * 100
                
                metrics = {}
                if hasattr(trainer_obj, 'metrics') and isinstance(trainer_obj.metrics, dict):
                    metrics = {k: float(v) for k, v in trainer_obj.metrics.items()}
                
                if job_id in training_jobs:
                    training_jobs[job_id]["progress"] = progress
                    training_jobs[job_id]["current_epoch"] = epoch
                    if metrics:
                        training_jobs[job_id]["metrics"] = metrics
                    if training_jobs[job_id].get("cancel_requested"):
                        trainer_obj.stop = True
                    _persist_job(job_id)
            except Exception as e:
                logger.error(f"Error in training callback: {e}")
                
        train_params["on_train_epoch_end"] = epoch_end_callback
        
        logger.info(f"Training parameters: {train_params}")
        results = trainer.train(**train_params)

        if training_jobs[job_id].get("cancel_requested"):
            upd = {
                "status": "cancelled",
                "progress": training_jobs[job_id].get("progress", 0),
                "current_epoch": training_jobs[job_id].get("current_epoch", 0),
                "cancelled_at": datetime.now().isoformat(),
            }
            if isinstance(results, dict):
                if results.get("model_path"):
                    upd["model_path"] = results.get("model_path", "")
                if results.get("metrics"):
                    upd["metrics"] = results.get("metrics", {})
            training_jobs[job_id].update(upd)
            _persist_job(job_id)
            logger.info(f"Training job {job_id} stopped by user")
            return

        training_jobs[job_id].update({
            "status": "completed",
            "progress": 100,
            "current_epoch": config.epochs,
            "results": results,
            "model_path": results.get("model_path", "") if isinstance(results, dict) else "",
            "metrics": results.get("metrics", {}) if isinstance(results, dict) else {},
            "per_class_metrics": results.get("per_class_metrics", []) if isinstance(results, dict) else [],
            "confusion_matrix_path": results.get("confusion_matrix_path") if isinstance(results, dict) else None,
            "completed_at": datetime.now().isoformat(),
        })
        _persist_job(job_id)
        logger.info(f"Training job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Training job {job_id} failed: {str(e)}", exc_info=True)
        if training_jobs.get(job_id, {}).get("cancel_requested"):
            training_jobs[job_id].update({
                "status": "cancelled",
                "progress": training_jobs[job_id].get("progress", 0),
                "cancelled_at": datetime.now().isoformat(),
            })
        else:
            training_jobs[job_id].update({
                "status": "failed",
                "error": str(e),
                "progress": training_jobs[job_id].get("progress", 0),
                "failed_at": datetime.now().isoformat(),
            })
        _persist_job(job_id)

@router.get("/status/{job_id}")
async def get_training_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get training job status
    """
    _ensure_jobs_loaded()
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return training_jobs[job_id]


@router.get("/job/{job_id}")
async def get_training_job_by_id(job_id: str, current_user: dict = Depends(get_current_user)):
    _ensure_jobs_loaded()
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return training_jobs[job_id]


@router.post("/cancel/{job_id}")
async def cancel_training_job(job_id: str, current_user: dict = Depends(get_current_user)):
    _ensure_jobs_loaded()
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = training_jobs[job_id]
    if not _job_owner_ok(job, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to cancel this job")
    status = job.get("status")
    if status not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{status}'")
    job["cancel_requested"] = True
    _persist_job(job_id)
    return {"success": True, "message": "Cancellation requested; training stops after the current epoch completes"}

@router.get("/queue-status")
async def get_queue_status(current_user: dict = Depends(get_current_user)):
    """
    Return current queue capacity so the UI can show slot availability and position.
    """
    _ensure_jobs_loaded()
    running = sum(1 for j in training_jobs.values() if j.get("status") == "running")
    pending_jobs = [
        {"job_id": jid, "created_at": j.get("created_at"), "dataset_id": j.get("dataset_id")}
        for jid, j in training_jobs.items() if j.get("status") == "pending"
    ]
    # Sort pending by creation time so callers know queue order
    pending_jobs.sort(key=lambda x: x.get("created_at") or "")
    return {
        "running": running,
        "pending": len(pending_jobs),
        "pending_jobs": pending_jobs,
        "max_concurrent": MAX_CONCURRENT_JOBS,
        "slots_available": max(0, MAX_CONCURRENT_JOBS - running),
    }


@router.get("/jobs")
async def list_training_jobs(current_user: dict = Depends(get_current_user)):
    """
    List all training jobs
    """
    _ensure_jobs_loaded()
    return {
        "jobs": [
            {"job_id": job_id, **job_data}
            for job_id, job_data in training_jobs.items()
        ]
    }

@router.delete("/job/{job_id}")
async def delete_training_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Remove a finished training job from the list. Use POST /cancel while running.
    """
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = training_jobs[job_id]
    if not _job_owner_ok(job, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")
    if job.get("status") in ("running", "pending"):
        raise HTTPException(status_code=400, detail="Cancel the job first; training is still in progress")
    del training_jobs[job_id]
    return {"success": True, "message": "Job deleted"}

@router.get("/job/{job_id}/metrics")
async def get_training_metrics(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get training metrics from results.csv
    """
    import pandas as pd
    import io
    
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Construct path to results.csv
    # The default YOLO project/name structure is runs/detect/{name}
    job_name = f"job_{job_id}"
    results_path = Path("runs/detect") / job_name / "results.csv"
    
    if not results_path.exists():
        # If training just started, results might not exist yet
        return {"metrics": []}
        
    try:
        # Read with pandas and standardise column names
        df = pd.read_csv(results_path)
        
        # Clean column names (strip spaces)
        df.columns = [c.strip() for c in df.columns]
        
        # Return as list of dicts
        return {"metrics": df.to_dict(orient="records")}
        
    except Exception as e:
        logger.error(f"Error reading metrics for {job_id}: {e}")
        return {"metrics": [], "error": str(e)}


@router.get("/preflight/{dataset_id}")
async def preflight_check(dataset_id: str):
    """
    Run pre-flight validation before training.
    Returns warnings (informational) and blockers (prevent training).
    """
    warnings = []
    blockers = []
    
    try:
        analysis = DatasetAnalyzer.analyze_dataset(dataset_id)
        
        # Check class balance — warn if any class has 10x more than another
        if analysis.class_frequency:
            counts = list(analysis.class_frequency.values())
            if len(counts) > 1:
                max_count = max(counts)
                min_count = min(counts)
                if min_count > 0 and max_count / min_count >= 10:
                    most = max(analysis.class_frequency, key=analysis.class_frequency.get)
                    least = min(analysis.class_frequency, key=analysis.class_frequency.get)
                    warnings.append({
                        "type": "class_imbalance",
                        "message": f"Severe class imbalance: '{most}' has {max_count} annotations vs '{least}' with {min_count}.",
                        "suggestion": "Consider oversampling the minority class, using class weights, or collecting more data for underrepresented classes."
                    })
                elif min_count > 0 and max_count / min_count >= 3:
                    warnings.append({
                        "type": "class_imbalance",
                        "message": f"Moderate class imbalance detected (ratio {max_count/min_count:.1f}x).",
                        "suggestion": "Enable mosaic and mixup augmentations to help with class balance."
                    })
        
        # Check corrupt images
        if analysis.corrupt_images:
            blockers.append({
                "type": "corrupt_images",
                "message": f"{len(analysis.corrupt_images)} corrupt image(s) detected.",
                "files": analysis.corrupt_images[:10],
                "suggestion": "Remove or re-upload these images before training."
            })
        
        # Check minimum annotated images
        if analysis.annotated_images < 5:
            blockers.append({
                "type": "insufficient_data",
                "message": f"Only {analysis.annotated_images} annotated images. Minimum 5 required.",
                "suggestion": "Annotate more images before starting training."
            })
        elif analysis.annotated_images < 20:
            warnings.append({
                "type": "low_data",
                "message": f"Only {analysis.annotated_images} annotated images. Results may be unreliable.",
                "suggestion": "Consider annotating at least 50+ images per class for better results."
            })
        
        # Check split distribution
        train_ratio = analysis.split_ratios.get("train", 0)
        val_ratio = analysis.split_ratios.get("val", 0)
        if train_ratio > 0 and val_ratio == 0:
            warnings.append({
                "type": "no_validation_split",
                "message": "No validation split detected. Model performance cannot be evaluated.",
                "suggestion": "Assign some images to the 'val' split, or use the auto-split feature."
            })
        
        # Check data leakage
        if analysis.data_leakage_detected:
            warnings.append({
                "type": "data_leakage",
                "message": "Duplicate images found across train/val splits.",
                "suggestion": "Remove duplicates to prevent inflated metrics."
            })
        
        # Overall quality
        quality_score = analysis.overall_quality_score
        
        return {
            "success": True,
            "dataset_id": dataset_id,
            "quality_score": round(quality_score, 1),
            "annotated_images": analysis.annotated_images,
            "total_annotations": analysis.total_annotations,
            "class_frequency": analysis.class_frequency,
            "warnings": warnings,
            "blockers": blockers,
            "can_train": len(blockers) == 0 
        }
    except Exception as e:
        logger.error(f"Preflight check failed: {e}")
        return {
            "success": False,
            "warnings": [],
            "blockers": [{"type": "error", "message": str(e), "suggestion": "Check server logs."}],
            "can_train": False
        }


@router.get("/job/{job_id}/confusion-matrix")
async def get_confusion_matrix(job_id: str):
    """
    Return the confusion matrix image for a completed training job.
    """
    from fastapi.responses import FileResponse
    
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_name = f"job_{job_id}"
    # YOLO saves confusion_matrix.png and confusion_matrix_normalized.png
    for variant in ["confusion_matrix_normalized.png", "confusion_matrix.png"]:
        cm_path = Path("runs/detect") / job_name / variant
        if cm_path.exists():
            return FileResponse(str(cm_path), media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Confusion matrix not available yet")


@router.get("/job/{job_id}/per-class-metrics")
async def get_per_class_metrics(job_id: str):
    """
    Return per-class precision, recall, mAP50 from the results.
    """
    import csv
    
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_name = f"job_{job_id}"
    results_dir = Path("runs/detect") / job_name
    
    # Try to read per-class metrics from results
    per_class = []
    
    # YOLO also saves results per class if available
    # We can extract from the results.csv or from the training results
    job = training_jobs[job_id]
    if "per_class_metrics" in job:
        per_class = job["per_class_metrics"]
    
    return {
        "success": True,
        "job_id": job_id,
        "per_class_metrics": per_class,
        "overall_metrics": job.get("metrics", {})
    }


@router.post("/auto-retrain-config")
async def set_auto_retrain_config(config: AutoRetrainConfig):
    """
    Configure auto-retrain triggers for a dataset.
    """
    auto_retrain_configs[config.dataset_id] = {
        "enabled": config.enabled,
        "min_new_annotations": config.min_new_annotations,
        "annotations_since_last_train": 0
    }
    return {
        "success": True,
        "config": auto_retrain_configs[config.dataset_id]
    }


@router.get("/auto-retrain-config/{dataset_id}")
async def get_auto_retrain_config(dataset_id: str):
    """
    Get auto-retrain configuration for a dataset.
    """
    config = auto_retrain_configs.get(dataset_id, {
        "enabled": False,
        "min_new_annotations": 50,
        "annotations_since_last_train": 0
    })
    return {"success": True, "config": config}


@router.get("/presets")
async def get_training_presets():
    """
    Return available training presets with descriptions.
    """
    return {
        "presets": {
            "fast": {
                "label": "Fast",
                "description": "Quick training for rapid iteration. Lower accuracy.",
                "epochs": 25, "batch_size": 32, "img_size": 416,
                "model_name": "yolov8n.pt", "patience": 10, "learning_rate": 0.01,
                "estimated_time": "~5 min"
            },
            "balanced": {
                "label": "Balanced",
                "description": "Good tradeoff between speed and accuracy.",
                "epochs": 100, "batch_size": 16, "img_size": 640,
                "model_name": "yolov8s.pt", "patience": 50, "learning_rate": 0.01,
                "estimated_time": "~30 min"
            },
            "accurate": {
                "label": "High Accuracy",
                "description": "Maximum accuracy. Best for production models.",
                "epochs": 300, "batch_size": 8, "img_size": 1024,
                "model_name": "yolov8m.pt", "patience": 80, "learning_rate": 0.001,
                "estimated_time": "~2 hours"
            }
        }
    }


@router.post("/start-from-dataset")
async def start_training_from_dataset(
    background_tasks: BackgroundTasks,
    request: DatasetTrainingRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Start training from an exported dataset. Auto-exports if not already exported.
    """
    _ensure_jobs_loaded()
    try:
        from app.core.access import require_role
        dataset = DatasetService.get_dataset(request.dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        require_role(request.dataset_id, current_user["id"], dataset["user_id"], "admin")

        active = sum(1 for j in training_jobs.values() if j.get("status") in ["running", "pending"])
        if active >= MAX_CONCURRENT_JOBS:
            raise HTTPException(
                status_code=429,
                detail=f"Too many training jobs running ({active}/{MAX_CONCURRENT_JOBS}). Wait for one to finish before starting another."
            )

        # Analyze dataset first
        try:
            analysis = DatasetAnalyzer.analyze_dataset(request.dataset_id)
            # Apply recommended augmentations if not manually specified
            if not request.config.augmentations:
                request.config.augmentations = analysis.augmentation_recommendations
                logger.info(f"Applied recommended augmentations: {request.config.augmentations}")
        except Exception as e:
            logger.warning(f"Failed to analyze dataset: {e}")

        version = DatasetVersionService.get_version(request.version_id)
        if not version or not version.get('yaml_path'):
            raise HTTPException(status_code=404, detail="Dataset version or generated YAML not found. Please generate a version first.")
            
        yaml_path = Path(version['yaml_path'])
        
        if not yaml_path.exists():
            raise HTTPException(status_code=404, detail="YAML file missing from disk.")
            
        train_images_dir = yaml_path.parent / 'train' / 'images'
        if not train_images_dir.exists() or not any(train_images_dir.iterdir()):
            raise HTTPException(status_code=400, detail="This dataset version has no training images. Please annotate some images and generate a new version before training.")
            
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Default config in job init
        training_jobs[job_id] = {
            "status": "pending",
            "config": request.config.dict(),
            "progress": 0,
            "version_id": request.version_id,
            "dataset_id": request.dataset_id,
            "created_at": datetime.now().isoformat(),
            "user_id": current_user["id"],
            "cancel_requested": False,
        }
        _persist_job(job_id)
        
        # Handle Class Filtering
        final_yaml_path = str(yaml_path)
        
        if request.classes:
            try:
                from utils.dataset_utils import create_filtered_dataset
                
                dataset_info = DatasetService.get_dataset(request.dataset_id)
                if dataset_info:
                    all_classes = dataset_info.get("classes", [])
                    
                    # Check if we actually need to filter (unordered set comparison)
                    if set(request.classes) != set(all_classes):
                        logger.info(f"Filtering dataset for classes: {request.classes}")
                        
                        # Create temporary directory for filtered dataset
                        temp_dir = Path(tempfile.gettempdir()) / "yolo_training" / job_id / "filtered"
                        
                        filtered_yaml = create_filtered_dataset(
                            original_yaml_path=str(yaml_path),
                            target_dir=str(temp_dir),
                            selected_classes=request.classes
                        )
                        final_yaml_path = filtered_yaml
                        logger.info(f"Created filtered dataset at: {final_yaml_path}")
                        
                        # Update job info to reflect filtering
                        training_jobs[job_id]["filtered_classes"] = request.classes
                        
            except Exception as e:
                logger.error(f"Failed to create filtered dataset: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to prepare filtered dataset: {str(e)}")

        
        # Add training to background tasks
        background_tasks.add_task(
            run_training,
            job_id,
            final_yaml_path,
            request.config
        )
        
        return JSONResponse(content={
            "success": True,
            "job_id": job_id,
            "message": "Training job started from dataset"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting training from dataset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export-and-train")
async def export_and_train(
    background_tasks: BackgroundTasks,
    request: ExportAndTrainRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Export dataset and start training in one operation (strict training mode)
    """
    _ensure_jobs_loaded()
    try:
        from app.core.access import require_role
        dataset = DatasetService.get_dataset(request.dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        require_role(request.dataset_id, current_user["id"], dataset["user_id"], "admin")

        # Analyze dataset first
        try:
            analysis = DatasetAnalyzer.analyze_dataset(request.dataset_id)
            # Apply recommended augmentations if not manually specified
            if not request.config.augmentations:
                request.config.augmentations = analysis.augmentation_recommendations
                logger.info(f"Applied recommended augmentations: {request.config.augmentations}")
        except Exception as e:
            logger.warning(f"Failed to analyze dataset: {e}")

        # Automatically generate a version for training
        versions = DatasetVersionService.list_dataset_versions(request.dataset_id)
        version_num = len(versions) + 1
        name = f"Auto-Train v{version_num}"
        
        try:
            engine = VersioningEngine()
            new_version_id = engine.generate_version(
                dataset_id=request.dataset_id,
                name=name,
                preprocessing={},
                augmentations=request.config.augmentations or {}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate dataset version for training: {str(e)}")
            
        if not new_version_id:
            raise HTTPException(status_code=500, detail="Failed to automatically generate version for training.")
            
        version = DatasetVersionService.get_version(new_version_id)
        if not version or not version.get('yaml_path'):
            raise HTTPException(status_code=404, detail="Dataset version or generated YAML not found.")
            
        yaml_path = Path(version['yaml_path'])
        
        # Force strict training mode
        request.config.strict_epochs = True
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Initialize training job
        training_jobs[job_id] = {
            "status": "pending",
            "config": request.config.dict(),
            "progress": 0,
            "version_id": new_version_id,
            "dataset_id": request.dataset_id,
            "strict_mode": True,
            "created_at": datetime.now().isoformat(),
            "user_id": current_user["id"],
            "cancel_requested": False,
        }
        _persist_job(job_id)
        
        # Add training to background tasks
        background_tasks.add_task(
            run_training,
            job_id,
            str(yaml_path),
            request.config
        )
        
        return JSONResponse(content={
            "success": True,
            "job_id": job_id,
            "message": "Dataset exported and strict training started",
            "strict_epochs": True,
            "epochs": request.config.epochs,
            "augmentations": request.config.augmentations
        })
        
    except Exception as e:
        logger.error(f"Export and train error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class PreviewAugmentationRequest(BaseModel):
    dataset_id: str
    preprocessing: Dict[str, Any] = {}
    augmentations: Dict[str, Any] = {}


@router.post("/preview-augmentation")
async def preview_augmentation(request: PreviewAugmentationRequest):
    """
    Preview augmentation on a random image from the dataset.
    Returns original and augmented images as base64.
    """
    import cv2
    import base64
    import random
    import numpy as np

    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    images = DatasetService.get_dataset_images(request.dataset_id)
    if not images:
        raise HTTPException(status_code=400, detail="No images in dataset")

    # Pick a random image
    img_data = random.choice(images)
    img_path = Path(img_data.get("path", ""))

    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    # Read image
    img = cv2.imread(str(img_path))
    if img is None:
        raise HTTPException(status_code=500, detail="Failed to read image")

    # Encode original as base64
    _, orig_buffer = cv2.imencode('.jpg', img)
    orig_b64 = base64.b64encode(orig_buffer).decode('utf-8')

    # Build augmentation pipeline using VersioningEngine
    engine = VersioningEngine()
    pipeline = engine._build_augmentation_pipeline(
        request.preprocessing, request.augmentations
    )

    # Apply augmentations
    try:
        augmented = pipeline(image=img)
        aug_img = augmented["image"]
    except Exception as e:
        logger.warning(f"Augmentation failed, returning original: {e}")
        aug_img = img

    # Encode augmented as base64
    _, aug_buffer = cv2.imencode('.jpg', aug_img)
    aug_b64 = base64.b64encode(aug_buffer).decode('utf-8')

    return {
        "success": True,
        "original": {
            "base64": orig_b64,
            "filename": img_data.get("filename", ""),
            "width": img.shape[1],
            "height": img.shape[0]
        },
        "augmented": {
            "base64": aug_b64,
            "width": aug_img.shape[1],
            "height": aug_img.shape[0]
        },
        "config": {
            "preprocessing": request.preprocessing,
            "augmentations": request.augmentations
        }
    }
