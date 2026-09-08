from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Form, Depends
from typing import Optional
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List
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
from app.services.base_trainer import TrainingCancelledException
from app.services.trainer_factory import create_trainer
from app.services.model_registry import get_allowed_model_keys, get_backend, get_model_info, get_registry_for_api
from app.services.dataset_analyzer import DatasetAnalyzer
from app.services.database import DatasetService, DatasetVersionService, TrainingJobService, AutoRetrainConfigService
from app.services.versioning import VersioningEngine
from app.api.v1.endpoints.auth import get_current_user
from utils.dataset_utils import split_dataset_stratified

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[4]  # …/server/
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

MAX_CONCURRENT_JOBS = 2

# ── Single-process invariant ─────────────────────────────────────────────────
# `training_jobs` is an in-process dict and MAX_CONCURRENT_JOBS is enforced by
# counting it, so the limit only holds while exactly one process serves the API.
# Run uvicorn with --workers 2 and each worker keeps its own registry: the cap
# silently becomes 2 per worker, cancellation reaches only the worker that owns
# the job, and a status poll routed to the other worker reports 404.
#
# Both start scripts are single-worker today. This check makes a future
# --workers flag fail loudly at import instead of corrupting job bookkeeping.
# Lifting it means moving job state to the DB (rows already exist via
# TrainingJobService) or to a real queue, and taking the capacity check with it.
def _assert_single_worker() -> None:
    workers = os.environ.get("WEB_CONCURRENCY") or os.environ.get("UVICORN_WORKERS")
    try:
        count = int(workers) if workers else 1
    except ValueError:
        return
    if count > 1:
        raise RuntimeError(
            f"NebulaML is configured for {count} workers, but training job state "
            "is per-process: the concurrency limit, cancellation and status polling "
            "all break across workers. Run a single worker, or move job state to the "
            "database before scaling out."
        )


_assert_single_worker()

training_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_loaded = False

def _ensure_jobs_loaded():
    global _jobs_loaded
    if not _jobs_loaded:
        try:
            persisted = TrainingJobService.load_all_jobs()
            # On startup, reconcile: any job marked running in the DB gets marked failed: orphaned_on_restart.
            # (In a multi-process setup, we would check if the PID is still alive here.)
            for jid, jdata in persisted.items():
                if jdata.get("status") in ("running", "pending"):
                    jdata["status"] = "failed"
                    jdata["error"] = "orphaned_on_restart"
                    try:
                        TrainingJobService.upsert_job(jid, jdata)
                    except Exception:
                        pass
            training_jobs.update(persisted)
            _jobs_loaded = True
            logger.info(f"Loaded {len(persisted)} training jobs from DB")
        except Exception as e:
            logger.warning(f"Could not load jobs from DB: {e}")
            _jobs_loaded = True

def _persist_job(job_id: str):
    """Persist full job state to DB — includes extended fields beyond the base schema."""
    try:
        job = training_jobs[job_id]
        # Build an enriched data dict so the DB load can restore all runtime fields
        enriched = dict(job)
        # Pack extended fields that the base upsert stores in the results JSON blob
        enriched.setdefault("results", {
            "metrics": job.get("metrics", {}),
            "model_path": job.get("model_path", ""),
            "per_class_metrics": job.get("per_class_metrics", []),
            "confusion_matrix_path": job.get("confusion_matrix_path"),
            "current_epoch": job.get("current_epoch", 0),
            "version_id": job.get("version_id"),
        })
        TrainingJobService.upsert_job(job_id, enriched)
    except Exception as e:
        logger.warning(f"Could not persist job {job_id}: {e}")


def _assert_capacity():
    """Reject the request if the training queue is full.

    Counts pending as well as running: a job sits in 'pending' between
    registration and the background task picking it up, so counting only
    'running' lets concurrent requests slip past the limit.
    """
    active = sum(1 for j in training_jobs.values() if j.get("status") in ("running", "pending"))
    if active >= MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many training jobs in progress ({active}/{MAX_CONCURRENT_JOBS}). "
                   "Wait for one to finish before starting another."
        )


def _job_owner_ok(job: Dict[str, Any], current_user: dict) -> bool:
    uid = job.get("user_id")
    if uid is None:
        return True
    return uid == current_user.get("id")


def _get_owned_job(job_id: str, current_user: dict) -> Dict[str, Any]:
    """Fetch a job the caller is allowed to see, or raise 404/403.

    Also loads persisted jobs first, so a job started before the last restart is
    still addressable.
    """
    _ensure_jobs_loaded()
    job = training_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not _job_owner_ok(job, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    return job

ALLOWED_MODELS = get_allowed_model_keys()

ALLOWED_OPTIMIZERS = {"auto", "SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSProp"}


class TrainingConfig(BaseModel):
    epochs: int = Field(default=100, ge=1, le=1000, description="Number of training epochs (1-1000)")
    batch_size: int = Field(default=16, ge=-1, le=128, description="Batch size (1-128), or -1 to size it automatically from available memory")
    img_size: int = Field(default=640, ge=320, le=1280, description="Image size (320-1280)")
    model_name: str = Field(default="yolov8n.pt", description="Base model name (yolov8, yolov9, yolov10, yolo11)")
    learning_rate: Optional[float] = Field(default=None, ge=0.00001, le=1.0, description="Initial learning rate (lr0)")
    patience: Optional[int] = Field(default=50, ge=1, le=200, description="Early stopping patience")
    device: Optional[str] = Field(default=None, description="Device (cpu, cuda, mps, or None for auto)")
    strict_epochs: bool = Field(default=False, description="If True, enforce exact epoch count (disable early stopping)")
    augmentations: Optional[Dict[str, Any]] = Field(default=None, description="Data augmentation parameters")
    preset: Optional[str] = Field(default=None, description="Preset name: fast, balanced, accurate")

    # Reproducibility
    seed: int = Field(default=0, ge=0, le=2_147_483_647, description="Random seed; the same seed and config reproduces a run")
    deterministic: bool = Field(default=True, description="Force deterministic algorithms. Slower, but makes runs exactly repeatable")

    # Optimisation schedule
    optimizer: str = Field(default="auto", description=f"One of {sorted(ALLOWED_OPTIMIZERS)}")
    lr_final: Optional[float] = Field(default=None, ge=0.0001, le=1.0, description="Final LR as a fraction of the initial LR (lrf)")
    weight_decay: Optional[float] = Field(default=None, ge=0.0, le=0.1, description="Optimizer weight decay")
    warmup_epochs: Optional[float] = Field(default=None, ge=0.0, le=20.0, description="Epochs of LR warmup before the main schedule")
    cos_lr: bool = Field(default=False, description="Use a cosine LR schedule instead of linear decay")

    # Throughput / memory
    workers: Optional[int] = Field(default=None, ge=0, le=16, description="Dataloader worker processes")
    cache: bool = Field(default=False, description="Cache images in RAM. Much faster per epoch on small datasets")
    amp: bool = Field(default=True, description="Mixed precision training")

    # Fine-tuning behaviour
    freeze: Optional[int] = Field(default=None, ge=0, le=24, description="Freeze the first N layers; useful for small datasets")
    dropout: Optional[float] = Field(default=None, ge=0.0, le=0.9, description="Dropout regularisation")
    close_mosaic: int = Field(default=10, ge=0, le=100, description="Disable mosaic augmentation for the final N epochs so the model settles on real images")
    save_period: int = Field(default=10, ge=-1, le=100, description="Checkpoint every N epochs (-1 disables), so an interrupted run can resume")

    @validator('model_name')
    def validate_model_name(cls, v):
        if v not in ALLOWED_MODELS:
            raise ValueError(f"Unsupported model '{v}'. Allowed: {sorted(ALLOWED_MODELS)}")
        return v

    @validator('optimizer')
    def validate_optimizer(cls, v):
        if v not in ALLOWED_OPTIMIZERS:
            raise ValueError(f"Unsupported optimizer '{v}'. Allowed: {sorted(ALLOWED_OPTIMIZERS)}")
        return v

    @validator('batch_size')
    def validate_batch_size(cls, v):
        # -1 means AutoBatch; anything else below 1 is meaningless.
        if v < 1 and v != -1:
            raise ValueError("Batch size must be at least 1, or -1 for automatic sizing")
        return v

    def apply_preset(self):
        """Apply a named preset, overriding defaults but not user-set values."""
        presets = {
            "fast": {"epochs": 25, "batch_size": 32, "img_size": 416, "model_name": "yolov8n.pt", "patience": 10, "learning_rate": 0.01},
            "balanced": {"epochs": 100, "batch_size": 16, "img_size": 640, "model_name": "yolov8s.pt", "patience": 50, "learning_rate": 0.01},
            "accurate": {"epochs": 300, "batch_size": 8, "img_size": 1024, "model_name": "yolov8m.pt", "patience": 80, "learning_rate": 0.001},
            "rtdetr_balanced": {
                "model_name": "rtdetr-r50",
                "epochs": 50,
                "batch_size": 4,
                "img_size": 640,
                "learning_rate": 0.00005,
                "patience": 20,
                "description": "RT-DETR balanced (Apache 2.0)"
            },
            "torchvision_fast": {
                "model_name": "fasterrcnn-mobilenet",
                "epochs": 30,
                "batch_size": 8,
                "img_size": 800,
                "learning_rate": 0.005,
                "patience": 15,
                "description": "Faster R-CNN MobileNet — fast (BSD)"
            },
        }
        if self.preset and self.preset in presets:
            p = presets[self.preset]
            set_fields = getattr(self, "__fields_set__", set())
            for k, v in p.items():
                if k not in set_fields:
                    setattr(self, k, v)
        return self

class DatasetTrainingRequest(BaseModel):
    dataset_id: str
    version_id: str
    config: TrainingConfig
    classes: Optional[List[str]] = None  # Optional list of class names to filter
    
class ExportAndTrainRequest(BaseModel):
    dataset_id: str
    config: TrainingConfig
    force: bool = False

class GenerateVersionRequest(BaseModel):
    dataset_id: str
    name: str = "Version 1"
    preprocessing: Dict[str, Any] = {}
    augmentations: Dict[str, Any] = {}
    force: bool = False

class AutoRetrainConfig(BaseModel):
    dataset_id: str
    enabled: bool = False
    min_new_annotations: int = Field(default=50, ge=10, le=1000)


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
    try:
        from app.services.versioning import DatasetDriftError
        version_id = engine.generate_version(
            dataset_id=request.dataset_id,
            name=request.name,
            preprocessing=request.preprocessing,
            augmentations=request.augmentations,
            force=request.force
        )
    except DatasetDriftError as e:
        return JSONResponse(
            status_code=409,
            content={"detail": str(e), "diff_summary": e.diff_summary}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
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
    from app.core.access import require_role
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")

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

    _assert_capacity()

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
            "model_type": get_backend(config.model_name),
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
    _assert_capacity()
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
            "model_type": get_backend(config.model_name),
        }
        _persist_job(job_id)

        background_tasks.add_task(run_training, job_id, str(yaml_path), config)
        
        return {"job_id": job_id, "status": "started"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start micro-training: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_training(job_id: str, data_yaml: str, config: TrainingConfig):
    """
    Background task to run training with strict validation
    """
    # Seeded before the try so the finally block is always well defined — an early
    # return or a failure on the very first statement used to raise UnboundLocalError
    # there, masking the real error.
    final_status = "failed"
    error_msg = "Training did not start"
    results: Dict[str, Any] = {}
    trainer = None

    try:
        training_jobs[job_id]["status"] = "running"
        training_jobs[job_id]["progress"] = 0
        training_jobs[job_id]["current_epoch"] = 0
        training_jobs[job_id]["cancel_requested"] = training_jobs[job_id].get("cancel_requested", False)
        _persist_job(job_id)

        if training_jobs[job_id].get("cancel_requested"):
            logger.info(f"Training job {job_id} cancelled before start")
            final_status = "cancelled"
            return

        logger.info(f"Starting training job {job_id} with {config.epochs} epochs")
        
        # Validate dataset YAML exists
        if not Path(data_yaml).exists():
            raise FileNotFoundError(f"Dataset YAML not found: {data_yaml}")
        
        # Initialize trainer
        trainer = create_trainer(config.model_name)
        
        # Training parameters with strict configuration
        train_params = {
            "data_yaml": data_yaml,
            "epochs": config.epochs,
            "imgsz": config.img_size,
            "batch": config.batch_size,
            "name": f"job_{job_id}",
            "project": str(_RUNS_BASE),
            "exist_ok": True,
            "strict_epochs": config.strict_epochs,  # Pass strict mode to trainer
        }
        
        # Reproducibility and schedule settings always apply.
        train_params.update({
            "seed": config.seed,
            "deterministic": config.deterministic,
            "optimizer": config.optimizer,
            "cos_lr": config.cos_lr,
            "amp": config.amp,
            "cache": config.cache,
            # Mosaic hurts in the final epochs; turning it off lets the model settle.
            "close_mosaic": min(config.close_mosaic, config.epochs),
            # Checkpoint regardless of strict mode so an interrupted run can resume.
            "save_period": config.save_period,
        })

        # Add optional parameters
        if config.learning_rate is not None:
            train_params["lr0"] = config.learning_rate
        if config.lr_final is not None:
            train_params["lrf"] = config.lr_final
        if config.weight_decay is not None:
            train_params["weight_decay"] = config.weight_decay
        if config.warmup_epochs is not None:
            train_params["warmup_epochs"] = config.warmup_epochs
        if config.workers is not None:
            train_params["workers"] = config.workers
        if config.freeze is not None:
            train_params["freeze"] = config.freeze
        if config.dropout is not None:
            train_params["dropout"] = config.dropout

        if config.strict_epochs:
            # In strict mode, disable early stopping - ensure all epochs run
            train_params["patience"] = config.epochs + 1
        elif config.patience:
            train_params["patience"] = config.patience

        if config.device:
            train_params["device"] = config.device

        # Add augmentations if present
        if config.augmentations:
            train_params["augmentations"] = config.augmentations

        def batch_end_callback(trainer_obj):
            if training_jobs.get(job_id, {}).get("cancel_requested"):
                raise TrainingCancelledException("Training cancelled by user")

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
                        raise TrainingCancelledException("Training cancelled by user")
                    _persist_job(job_id)
            except TrainingCancelledException:
                raise
            except Exception as e:
                logger.error(f"Error in training callback: {e}")
                
        train_params["on_train_epoch_end"] = epoch_end_callback
        train_params["on_train_batch_end"] = batch_end_callback
        train_params["job_info"] = training_jobs[job_id]
        
        logger.info(f"Training parameters: {train_params}")
        results = await asyncio.to_thread(trainer.train, **train_params)
        
        # Task 1: increment weights_version
        training_jobs[job_id]["weights_version"] = training_jobs[job_id].get("weights_version", 0) + 1

        final_status = "completed"


    except TrainingCancelledException:
        logger.info(f"Training job {job_id} cancelled by user")
        final_status = "cancelled"

    except Exception as e:
        logger.error(f"Training job {job_id} failed: {str(e)}", exc_info=True)
        final_status = "failed"
        error_msg = str(e)


    finally:
        # Task 3: Ensure GPU memory is released before the job slot is freed
        if trainer is not None:
            if hasattr(trainer, "model"):
                trainer.model = None
            trainer = None

        import torch
        import gc
        gc.collect()
        
        mem_before = 0
        mem_after = 0
        if torch.cuda.is_available():
            mem_before = torch.cuda.memory_allocated()
            torch.cuda.empty_cache()
            mem_after = torch.cuda.memory_allocated()
            logger.info(f"GPU memory cleanup (CUDA): {mem_before} -> {mem_after} bytes")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            torch.mps.empty_cache()
            logger.info("GPU memory cleanup (MPS) completed")
            
        # Only after cleanup, we update the DB and mark the slot free
        if final_status == "completed":
            training_jobs[job_id].update({
                "status": "completed",
                "progress": 100,
                # Early stopping can finish short of config.epochs.
                "current_epoch": results.get("epochs_completed", config.epochs),
                "results": results,
                "model_path": results.get("model_path", ""),
                "metrics": results.get("metrics", {}),
                "per_class_metrics": results.get("per_class_metrics", []),
                "confusion_matrix_path": results.get("confusion_matrix_path"),
                "completed_at": datetime.now().isoformat(),
            })
        elif final_status == "cancelled":
            training_jobs[job_id].update({
                "status": "cancelled",
                "progress": training_jobs[job_id].get("progress", 0),
                "cancelled_at": datetime.now().isoformat(),
            })
        elif final_status == "failed":
            training_jobs[job_id].update({
                "status": "failed",
                "error": error_msg,
                "progress": training_jobs[job_id].get("progress", 0),
                "failed_at": datetime.now().isoformat(),
            })
            
        _persist_job(job_id)
        if final_status == "completed":
            logger.info(f"Training job {job_id} completed successfully")

@router.get("/status/{job_id}")
async def get_training_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get training job status
    """
    return _get_owned_job(job_id, current_user)


@router.get("/job/{job_id}")
async def get_training_job_by_id(job_id: str, current_user: dict = Depends(get_current_user)):
    return _get_owned_job(job_id, current_user)

@router.get("/job/{job_id}/stream")
async def stream_job_details(job_id: str, current_user: dict = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse
    
    _get_owned_job(job_id, current_user)

    async def event_stream():
        last_signature = None
        while True:
            # Re-fetch the job from the dict to get latest reference
            current_job = training_jobs.get(job_id)
            if not current_job:
                break

            status = current_job.get("status")
            signature = (status, current_job.get("current_epoch"), current_job.get("progress"))

            # Only push when something actually changed; a terminal status always
            # gets one final frame so the client can close cleanly.
            terminal = status in ("completed", "failed", "cancelled", "success")
            if signature != last_signature or terminal:
                last_signature = signature
                # Omit full output to prevent massive payloads
                payload_dict = current_job.copy()
                if "output" in payload_dict and len(payload_dict["output"]) > 1000:
                    payload_dict["output"] = payload_dict["output"][-1000:]
                yield f"data: {json.dumps(payload_dict, default=str)}\n\n"
            else:
                yield ": keep-alive\n\n"

            if terminal:
                break

            await asyncio.sleep(2.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/cancel/{job_id}")
async def cancel_training_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = _get_owned_job(job_id, current_user)
    status = job.get("status")
    if status not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{status}'")
    job["cancel_requested"] = True
    _persist_job(job_id)
    return {"success": True, "message": "Cancellation requested; training stops at the next batch boundary"}

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
        "slots_available": max(0, MAX_CONCURRENT_JOBS - running - len(pending_jobs)),
    }


@router.get("/jobs")
async def list_training_jobs(current_user: dict = Depends(get_current_user)):
    """
    List all training jobs
    """
    _ensure_jobs_loaded()
    uid = current_user.get("id")
    return {
        "jobs": [
            {"job_id": job_id, **job_data}
            for job_id, job_data in training_jobs.items()
            if job_data.get("user_id") is None or job_data.get("user_id") == uid
        ]
    }

@router.delete("/job/{job_id}")
async def delete_training_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Remove a finished training job from the list. Use POST /cancel while running.
    """
    job = _get_owned_job(job_id, current_user)
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
    
    _get_owned_job(job_id, current_user)

    # Must match the project dir run_training passes to the trainer.
    results_path = _RUNS_BASE / f"job_{job_id}" / "results.csv"
    
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
async def preflight_check(dataset_id: str, current_user: dict = Depends(get_current_user)):
    """
    Run pre-flight validation before training using the new pipeline stages.
    """
    try:
        from app.services.preflight import PreflightPipeline
        return PreflightPipeline.run_all(dataset_id)
    except Exception as e:
        logger.error(f"Preflight check failed: {e}")
        return {
            "success": False,
            "reports": [],
            "warnings": [],
            "blockers": [{"stage": "System", "check": "execution_error", "severity": "blocking", "message": str(e)}],
            "can_train": False
        }


@router.get("/job/{job_id}/confusion-matrix")
async def get_confusion_matrix(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Return the confusion matrix image for a completed training job.
    """
    from fastapi.responses import FileResponse
    
    _get_owned_job(job_id, current_user)

    # YOLO saves confusion_matrix.png and confusion_matrix_normalized.png
    for variant in ["confusion_matrix_normalized.png", "confusion_matrix.png"]:
        cm_path = _RUNS_BASE / f"job_{job_id}" / variant
        if cm_path.exists():
            return FileResponse(str(cm_path), media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Confusion matrix not available yet")


@router.get("/job/{job_id}/per-class-metrics")
async def get_per_class_metrics(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Return per-class precision, recall, mAP50 from the results.
    """
    job = _get_owned_job(job_id, current_user)
    per_class = job.get("per_class_metrics", [])

    return {
        "success": True,
        "job_id": job_id,
        "per_class_metrics": per_class,
        "overall_metrics": job.get("metrics", {})
    }

@router.get("/model-registry")
async def get_model_registry():
    """Return the full model registry for client-side model selection."""
    return {"models": get_registry_for_api()}


@router.post("/auto-retrain-config")
async def set_auto_retrain_config(config: AutoRetrainConfig, current_user: dict = Depends(get_current_user)):
    """
    Configure auto-retrain triggers for a dataset. Persisted to MySQL.
    """
    AutoRetrainConfigService.upsert_config(
        dataset_id=config.dataset_id,
        enabled=config.enabled,
        min_new_annotations=config.min_new_annotations,
    )
    saved = AutoRetrainConfigService.get_config(config.dataset_id)
    return {"success": True, "config": saved}


@router.get("/auto-retrain-config/{dataset_id}")
async def get_auto_retrain_config(dataset_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get auto-retrain configuration for a dataset.
    """
    config = AutoRetrainConfigService.get_config(dataset_id)
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

        _assert_capacity()

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
    _assert_capacity()
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
            from app.services.versioning import DatasetDriftError
            engine = VersioningEngine()
            new_version_id = engine.generate_version(
                dataset_id=request.dataset_id,
                name=name,
                preprocessing={},
                augmentations=request.config.augmentations or {},
                force=request.force
            )
        except DatasetDriftError as e:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=409,
                content={"detail": str(e), "diff_summary": e.diff_summary}
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export and train error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class PreviewAugmentationRequest(BaseModel):
    dataset_id: str
    preprocessing: Dict[str, Any] = {}
    augmentations: Dict[str, Any] = {}


@router.post("/preview-augmentation")
async def preview_augmentation(request: PreviewAugmentationRequest, current_user: dict = Depends(get_current_user)):
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
