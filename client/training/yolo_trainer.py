"""
YOLOv8 Training Service

This module provides a comprehensive training service for YOLOv8 models with:
- Start/stop/resume training
- Model export (ONNX, TorchScript)
- GPU auto-detection
- Batch size auto-tuning
- Log saving
- Metrics tracking
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import torch
from ultralytics import YOLO
from ultralytics.utils import LOGGER as YOLO_LOGGER


@dataclass
class TrainingConfig:
    """Training configuration."""
    epochs: int = 100
    batch_size: int = 16
    img_size: int = 640
    model_name: str = "yolov8n.pt"
    dataset_yaml: Optional[str] = None
    device: Optional[str] = None  # 'cpu', 'cuda', 'mps', or None for auto
    workers: int = 8
    patience: int = 50  # Early stopping patience
    save_period: int = 10  # Save checkpoint every N epochs
    project: str = "runs/detect"
    name: str = "train"
    exist_ok: bool = True
    resume: bool = False
    resume_path: Optional[str] = None
    optimizer: str = "SGD"
    lr0: float = 0.01
    lrf: float = 0.01
    momentum: float = 0.937
    weight_decay: float = 0.0005
    warmup_epochs: float = 3.0
    warmup_momentum: float = 0.8
    warmup_bias_lr: float = 0.1
    box: float = 7.5
    cls: float = 0.5
    dfl: float = 1.5
    pose: float = 12.0
    kobj: float = 2.0
    label_smoothing: float = 0.0
    nbs: int = 64  # Nominal batch size
    hsv_h: float = 0.015
    hsv_s: float = 0.7
    hsv_v: float = 0.4
    degrees: float = 0.0
    translate: float = 0.1
    scale: float = 0.5
    shear: float = 0.0
    perspective: float = 0.0
    flipud: float = 0.0
    fliplr: float = 0.5
    mosaic: float = 1.0
    mixup: float = 0.0
    copy_paste: float = 0.0


@dataclass
class TrainingMetrics:
    """Training metrics."""
    epoch: int = 0
    train_loss: float = 0.0
    val_loss: float = 0.0
    mAP50: float = 0.0
    mAP50_95: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    learning_rate: float = 0.0
    progress_percent: float = 0.0
    elapsed_time: float = 0.0
    estimated_time_remaining: float = 0.0


@dataclass
class TrainingJob:
    """Training job information."""
    job_id: str
    status: str  # 'pending', 'running', 'paused', 'completed', 'failed', 'stopped'
    config: TrainingConfig
    metrics: TrainingMetrics = field(default_factory=TrainingMetrics)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    log_path: Optional[str] = None
    model_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class YOLOTrainer:
    """YOLOv8 Training Service."""
    
    def __init__(self, jobs_dir: Union[str, Path] = "training/jobs", 
                 logs_dir: Union[str, Path] = "training/logs"):
        """
        Initialize YOLO trainer.
        
        Args:
            jobs_dir: Directory to store job information
            logs_dir: Directory to store training logs
        """
        self.jobs_dir = Path(jobs_dir)
        self.logs_dir = Path(logs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.active_jobs: Dict[str, TrainingJob] = {}
        self.training_threads: Dict[str, threading.Thread] = {}
        self.stop_flags: Dict[str, threading.Event] = {}
        self.pause_flags: Dict[str, threading.Event] = {}
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # GPU detection
        self.device_info = self._detect_device()
        self.logger.info(f"Device info: {self.device_info}")
    
    def _detect_device(self) -> Dict[str, Any]:
        """Auto-detect available device and capabilities."""
        device_info = {
            "cuda_available": torch.cuda.is_available(),
            "mps_available": hasattr(torch.backends, 'mps') and torch.backends.mps.is_available(),
            "device": "cpu",
            "device_count": 0,
            "device_name": "CPU",
            "memory_gb": 0.0
        }
        
        if device_info["cuda_available"]:
            device_info["device"] = "cuda"
            device_info["device_count"] = torch.cuda.device_count()
            device_info["device_name"] = torch.cuda.get_device_name(0)
            device_info["memory_gb"] = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        elif device_info["mps_available"]:
            device_info["device"] = "mps"
            device_info["device_name"] = "Apple Silicon GPU"
        
        return device_info
    
    def _auto_tune_batch_size(self, config: TrainingConfig, model: YOLO, 
                              dataset_yaml: str) -> int:
        """
        Auto-tune batch size based on available memory.
        
        Args:
            config: Training configuration
            model: YOLO model instance
            dataset_yaml: Path to dataset YAML
        
        Returns:
            Optimal batch size
        """
        self.logger.info("Auto-tuning batch size...")
        
        # Start with the configured batch size
        batch_size = config.batch_size
        max_batch_size = 128
        
        # Try increasing batch size until OOM or max reached
        for test_batch in [batch_size, batch_size * 2, batch_size * 4, max_batch_size]:
            if test_batch > max_batch_size:
                break
            
            try:
                # Test with a single epoch
                test_config = asdict(config)
                test_config["epochs"] = 1
                test_config["batch_size"] = test_batch
                
                # Temporarily suppress output
                import sys
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                
                try:
                    model.train(
                        data=dataset_yaml,
                        epochs=1,
                        batch=test_batch,
                        imgsz=config.img_size,
                        device=config.device or self.device_info["device"],
                        verbose=False
                    )
                    batch_size = test_batch
                    self.logger.info(f"Batch size {test_batch} works")
                except RuntimeError as e:
                    if "out of memory" in str(e).lower():
                        self.logger.info(f"Batch size {test_batch} causes OOM, using {batch_size}")
                        break
                    else:
                        raise
                finally:
                    sys.stdout = old_stdout
                    
            except Exception as e:
                self.logger.warning(f"Error testing batch size {test_batch}: {e}")
                break
        
        self.logger.info(f"Auto-tuned batch size: {batch_size}")
        return batch_size
    
    def start_training(self, job_id: str, config: TrainingConfig) -> TrainingJob:
        """
        Start a new training job.
        
        Args:
            job_id: Unique job identifier
            config: Training configuration
        
        Returns:
            TrainingJob object
        """
        if job_id in self.active_jobs:
            raise ValueError(f"Job {job_id} already exists")
        
        # Validate dataset YAML
        if not config.dataset_yaml:
            raise ValueError("dataset_yaml is required")
        
        dataset_path = Path(config.dataset_yaml)
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset YAML not found: {config.dataset_yaml}")
        
        # Create job
        job = TrainingJob(
            job_id=job_id,
            status="pending",
            config=config
        )
        
        # Set device if not specified
        if not config.device:
            config.device = self.device_info["device"]
        
        # Auto-tune batch size if needed (can be done in thread)
        # For now, use configured batch size
        
        self.active_jobs[job_id] = job
        self.stop_flags[job_id] = threading.Event()
        self.pause_flags[job_id] = threading.Event()
        
        # Start training thread
        thread = threading.Thread(
            target=self._training_worker,
            args=(job_id,),
            daemon=True
        )
        thread.start()
        self.training_threads[job_id] = thread
        
        return job
    
    def _training_worker(self, job_id: str):
        """Worker thread for training."""
        job = self.active_jobs[job_id]
        stop_event = self.stop_flags[job_id]
        pause_event = self.pause_flags[job_id]
        
        try:
            job.status = "running"
            job.start_time = time.time()
            
            # Setup log file
            log_file = self.logs_dir / f"{job_id}.log"
            job.log_path = str(log_file)
            
            # Setup file handler for logging
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
            try:
                # Load model
                model = YOLO(job.config.model_name)
                
                # Auto-tune batch size (optional, can be disabled for faster startup)
                # batch_size = self._auto_tune_batch_size(job.config, model, job.config.dataset_yaml)
                # job.config.batch_size = batch_size
                
                # Prepare training arguments
                train_args = {
                    "data": job.config.dataset_yaml,
                    "epochs": job.config.epochs,
                    "batch": job.config.batch_size,
                    "imgsz": job.config.img_size,
                    "device": job.config.device,
                    "workers": job.config.workers,
                    "patience": job.config.patience,
                    "save_period": job.config.save_period,
                    "project": job.config.project,
                    "name": f"{job.config.name}_{job_id}",
                    "exist_ok": job.config.exist_ok,
                    "optimizer": job.config.optimizer,
                    "lr0": job.config.lr0,
                    "lrf": job.config.lrf,
                    "momentum": job.config.momentum,
                    "weight_decay": job.config.weight_decay,
                    "warmup_epochs": job.config.warmup_epochs,
                    "warmup_momentum": job.config.warmup_momentum,
                    "warmup_bias_lr": job.config.warmup_bias_lr,
                    "box": job.config.box,
                    "cls": job.config.cls,
                    "dfl": job.config.dfl,
                    "label_smoothing": job.config.label_smoothing,
                    "nbs": job.config.nbs,
                    "hsv_h": job.config.hsv_h,
                    "hsv_s": job.config.hsv_s,
                    "hsv_v": job.config.hsv_v,
                    "degrees": job.config.degrees,
                    "translate": job.config.translate,
                    "scale": job.config.scale,
                    "shear": job.config.shear,
                    "perspective": job.config.perspective,
                    "flipud": job.config.flipud,
                    "fliplr": job.config.fliplr,
                    "mosaic": job.config.mosaic,
                    "mixup": job.config.mixup,
                    "copy_paste": job.config.copy_paste,
                }
                
                # Handle resume
                if job.config.resume and job.config.resume_path:
                    train_args["resume"] = job.config.resume_path
                
                # Custom callback to check for stop/pause
                class TrainingCallback:
                    def __init__(self, job_ref, stop_event, pause_event):
                        self.job_ref = job_ref
                        self.stop_event = stop_event
                        self.pause_event = pause_event
                    
                    def on_train_epoch_end(self, trainer):
                        # Check for stop
                        if self.stop_event.is_set():
                            trainer.stop = True
                            return
                        
                        # Handle pause (simple implementation)
                        while self.pause_event.is_set():
                            time.sleep(0.1)
                            if self.stop_event.is_set():
                                trainer.stop = True
                                return
                        
                        # Update metrics (simplified - in real implementation, parse from trainer)
                        # This would need to be integrated with Ultralytics callbacks
                        pass
                
                callback = TrainingCallback(job, stop_event, pause_event)
                model.add_callback('on_train_epoch_end', callback.on_train_epoch_end)
                
                # Start training
                self.logger.info(f"Starting training for job {job_id}")
                results = model.train(**train_args)
                
                # Training completed
                job.status = "completed"
                job.end_time = time.time()
                
                # Extract final metrics
                if hasattr(results, 'results_dict'):
                    metrics = results.results_dict
                    job.metrics.mAP50 = metrics.get('metrics/mAP50(B)', 0.0)
                    job.metrics.mAP50_95 = metrics.get('metrics/mAP50-95(B)', 0.0)
                    job.metrics.precision = metrics.get('metrics/precision(B)', 0.0)
                    job.metrics.recall = metrics.get('metrics/recall(B)', 0.0)
                
                # Find model path
                run_dir = Path(job.config.project) / f"{job.config.name}_{job_id}"
                best_model = run_dir / "weights" / "best.pt"
                if best_model.exists():
                    job.model_path = str(best_model)
                
                self.logger.info(f"Training completed for job {job_id}")
                
            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)
                job.end_time = time.time()
                self.logger.error(f"Training failed for job {job_id}: {e}", exc_info=True)
            
            finally:
                # Save job state
                self._save_job(job)
                if file_handler in self.logger.handlers:
                    self.logger.removeHandler(file_handler)
        
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.end_time = time.time()
            self.logger.error(f"Fatal error in training worker for job {job_id}: {e}", exc_info=True)
            self._save_job(job)
    
    def stop_training(self, job_id: str) -> bool:
        """
        Stop a running training job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if stopped successfully
        """
        if job_id not in self.active_jobs:
            return False
        
        job = self.active_jobs[job_id]
        if job.status != "running":
            return False
        
        self.stop_flags[job_id].set()
        job.status = "stopped"
        job.end_time = time.time()
        self._save_job(job)
        
        return True
    
    def pause_training(self, job_id: str) -> bool:
        """
        Pause a running training job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if paused successfully
        """
        if job_id not in self.active_jobs:
            return False
        
        job = self.active_jobs[job_id]
        if job.status != "running":
            return False
        
        self.pause_flags[job_id].set()
        job.status = "paused"
        self._save_job(job)
        
        return True
    
    def resume_training(self, job_id: str) -> bool:
        """
        Resume a paused training job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if resumed successfully
        """
        if job_id not in self.active_jobs:
            return False
        
        job = self.active_jobs[job_id]
        if job.status != "paused":
            return False
        
        # Set resume flag and update config
        job.config.resume = True
        # Find the last checkpoint
        run_dir = Path(job.config.project) / f"{job.config.name}_{job_id}"
        last_ckpt = run_dir / "weights" / "last.pt"
        if last_ckpt.exists():
            job.config.resume_path = str(last_ckpt)
        
        self.pause_flags[job_id].clear()
        job.status = "running"
        self._save_job(job)
        
        # Restart training thread
        if job_id in self.training_threads:
            thread = threading.Thread(
                target=self._training_worker,
                args=(job_id,),
                daemon=True
            )
            thread.start()
            self.training_threads[job_id] = thread
        
        return True
    
    def export_model(self, job_id: str, format: str = "onnx", 
                    imgsz: int = 640) -> Optional[str]:
        """
        Export trained model to specified format.
        
        Args:
            job_id: Job identifier
            format: Export format ('onnx', 'torchscript', 'tflite', etc.)
            imgsz: Image size for export
        
        Returns:
            Path to exported model or None if failed
        """
        if job_id not in self.active_jobs:
            return None
        
        job = self.active_jobs[job_id]
        if not job.model_path or not Path(job.model_path).exists():
            # Try to find the model
            run_dir = Path(job.config.project) / f"{job.config.name}_{job_id}"
            model_path = run_dir / "weights" / "best.pt"
            if not model_path.exists():
                return None
        else:
            model_path = Path(job.model_path)
        
        try:
            model = YOLO(str(model_path))
            export_path = model.export(format=format, imgsz=imgsz)
            return str(export_path)
        except Exception as e:
            self.logger.error(f"Export failed for job {job_id}: {e}")
            return None
    
    def get_job(self, job_id: str) -> Optional[TrainingJob]:
        """Get job information."""
        return self.active_jobs.get(job_id)
    
    def list_jobs(self) -> List[TrainingJob]:
        """List all jobs."""
        return list(self.active_jobs.values())
    
    def get_metrics(self, job_id: str) -> Optional[TrainingMetrics]:
        """Get current training metrics for a job."""
        job = self.active_jobs.get(job_id)
        if job:
            return job.metrics
        return None
    
    def _save_job(self, job: TrainingJob):
        """Save job state to disk."""
        job_file = self.jobs_dir / f"{job.job_id}.json"
        job_dict = asdict(job)
        # Convert Path objects to strings
        for key, value in job_dict.items():
            if isinstance(value, Path):
                job_dict[key] = str(value)
        
        with open(job_file, 'w') as f:
            json.dump(job_dict, f, indent=2, default=str)
    
    def load_job(self, job_id: str) -> Optional[TrainingJob]:
        """Load job from disk."""
        job_file = self.jobs_dir / f"{job_id}.json"
        if not job_file.exists():
            return None
        
        with open(job_file, 'r') as f:
            job_dict = json.load(f)
        
        # Reconstruct job object
        config_dict = job_dict.pop('config', {})
        config = TrainingConfig(**config_dict)
        metrics_dict = job_dict.pop('metrics', {})
        metrics = TrainingMetrics(**metrics_dict)
        
        job = TrainingJob(
            job_id=job_dict['job_id'],
            status=job_dict['status'],
            config=config,
            metrics=metrics,
            start_time=job_dict.get('start_time'),
            end_time=job_dict.get('end_time'),
            log_path=job_dict.get('log_path'),
            model_path=job_dict.get('model_path'),
            error_message=job_dict.get('error_message'),
            created_at=job_dict.get('created_at', time.time())
        )
        
        return job
