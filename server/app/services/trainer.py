import ultralytics
from ultralytics import YOLO
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import torch

class TrainingCancelledException(Exception):
    pass

class YOLOTrainer:
    """YOLO model training handler"""
    
    def __init__(self, model_name: str = "yolov8n.pt"):
        """
        Initialize YOLO trainer
        
        Args:
            model_name: Base model to start training from
        """
        self.model_name = model_name
        self.model = YOLO(model_name)
        # Task 4: Move device detection to be computed per-job inside train()
        
    def train(
        self,
        data_yaml: str,
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        name: str = "yolo_custom",
        strict_epochs: bool = False,
        augmentations: Optional[Dict[str, Any]] = None,
        job_info: Optional[Dict[str, Any]] = None, # Used to update training_jobs with detected device
        **kwargs
    ) -> Dict[str, Any]:
        """
        Train YOLO model
        
        Args:
            data_yaml: Path to dataset YAML configuration
            epochs: Number of training epochs (MANDATORY if strict_epochs=True)
            imgsz: Input image size
            batch: Batch size
            name: Training run name
            strict_epochs: If True, enforce exact epoch count (disable early stopping)
            augmentations: Dictionary of augmentation parameters (mosaic, mixup, etc.)
            job_info: Dictionary containing the job_id (to update device_used)
            **kwargs: Additional training arguments
            
        Returns:
            Training results dictionary
        """
        # Validate epochs
        if epochs < 1:
            raise ValueError(f"Epochs must be at least 1, got {epochs}")
        if epochs > 1000:
            raise ValueError(f"Epochs cannot exceed 1000, got {epochs}")
            
        # Task 4: Per-job device detection
        device = kwargs.pop('device', None)
        if not device:
            if torch.cuda.is_available():
                device = 'cuda'
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = 'mps'
            else:
                device = 'cpu'
        
        self.device = device
        if job_info is not None:
            job_info['device_used'] = self.device
        
        # If strict mode, disable early stopping by setting patience very high
        if strict_epochs:
            kwargs['patience'] = epochs + 1  # Ensure all epochs run
            kwargs['save_period'] = kwargs.get('save_period', 10)  # Save checkpoints
            
        # Apply YOLO-supported augmentations if provided
        if augmentations:
            yolo_supported = [
                'hsv_h', 'hsv_s', 'hsv_v', 'degrees', 'translate', 'scale', 
                'shear', 'perspective', 'flipud', 'fliplr', 'mosaic', 'mixup', 
                'copy_paste', 'auto_augment', 'erasing', 'crop_fraction'
            ]
            valid_augs = {k: v for k, v in augmentations.items() if k in yolo_supported}
            kwargs.update(valid_augs)
            
        on_train_epoch_end = kwargs.pop('on_train_epoch_end', None)
        if on_train_epoch_end:
            self.model.add_callback('on_train_epoch_end', on_train_epoch_end)

        on_train_batch_end = kwargs.pop('on_train_batch_end', None)
        if on_train_batch_end:
            self.model.add_callback('on_train_batch_end', on_train_batch_end)

        results = self.model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            name=name,
            device=device,
            **kwargs
        )
        
        best_model_path = str(results.save_dir / "weights" / "best.pt")
        
        # Task 5: Only export ONNX if we haven't raised TrainingCancelledException
        # Note: If train() raises an exception, we won't reach this code. 
        # But if the user didn't request cancellation or we completed, we export.
        onnx_export_status = "skipped"
        if Path(best_model_path).exists() and Path(best_model_path).stat().st_size > 0:
            try:
                best_model = YOLO(best_model_path)
                best_model.export(format="onnx")
                onnx_export_status = "success"
            except Exception as e:
                print(f"ONNX export failed: {e}")
                onnx_export_status = "failed"
                
        # Extract per-class metrics if available
        per_class_metrics = []
        try:
            if hasattr(results, 'box') and results.box is not None:
                # results.box contains per-class metrics
                box = results.box
                class_names = results.names if hasattr(results, 'names') else {}
                
                if hasattr(box, 'ap50') and box.ap50 is not None:
                    for i in range(len(box.ap50)):
                        cls_name = class_names.get(i, f"class_{i}")
                        per_class_metrics.append({
                            "class_id": i,
                            "class_name": cls_name,
                            "precision": float(box.p[i]) if hasattr(box, 'p') and i < len(box.p) else 0,
                            "recall": float(box.r[i]) if hasattr(box, 'r') and i < len(box.r) else 0,
                            "mAP50": float(box.ap50[i]),
                            "mAP50_95": float(box.ap[i]) if hasattr(box, 'ap') and i < len(box.ap) else 0,
                        })
        except Exception as e:
            print(f"Could not extract per-class metrics: {e}")
        
        # Check for confusion matrix
        confusion_matrix_path = None
        for variant in ["confusion_matrix_normalized.png", "confusion_matrix.png"]:
            cm_path = results.save_dir / variant
            if cm_path.exists():
                confusion_matrix_path = str(cm_path)
                break
        
        epochs_completed = epochs
        try:
            import pandas as pd
            results_csv = results.save_dir / "results.csv"
            if results_csv.exists():
                df = pd.read_csv(results_csv)
                epochs_completed = len(df)
        except Exception:
            pass

        return {
            "success": True,
            "epochs_completed": epochs_completed,
            "model_path": best_model_path,
            "results_dir": str(results.save_dir),
            "onnx_export_status": onnx_export_status,
            "metrics": {
                "map50": float(results.results_dict.get("metrics/mAP50(B)", 0)),
                "map50-95": float(results.results_dict.get("metrics/mAP50-95(B)", 0)),
                "precision": float(results.results_dict.get("metrics/precision(B)", 0)),
                "recall": float(results.results_dict.get("metrics/recall(B)", 0)),
            },
            "per_class_metrics": per_class_metrics,
            "confusion_matrix_path": confusion_matrix_path,
        }
    
    def validate(self, data_yaml: str) -> Dict[str, Any]:
        """
        Validate model on dataset
        
        Args:
            data_yaml: Path to dataset YAML
            
        Returns:
            Validation metrics
        """
        metrics = self.model.val(data=data_yaml, device=self.device)
        
        return {
            "map50": float(metrics.box.map50),
            "map50-95": float(metrics.box.map),
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr)
        }
    
    def export_model(self, format: str = "onnx") -> str:
        """
        Export model to different format
        
        Args:
            format: Export format (onnx, torchscript, etc.)
            
        Returns:
            Path to exported model
        """
        path = self.model.export(format=format)
        return str(path)

