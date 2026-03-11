from ultralytics import YOLO
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import torch

class YOLOTrainer:
    """YOLO model training handler"""
    
    def __init__(self, model_name: str = "yolov8n.pt"):
        """
        Initialize YOLO trainer
        
        Args:
            model_name: Base model to start training from
        """
        self.model = YOLO(model_name)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
    def train(
        self,
        data_yaml: str,
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        name: str = "yolo_custom",
        strict_epochs: bool = False,
        augmentations: Optional[Dict[str, Any]] = None,
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
            **kwargs: Additional training arguments
            
        Returns:
            Training results dictionary
        """
        # Validate epochs
        if epochs < 1:
            raise ValueError(f"Epochs must be at least 1, got {epochs}")
        if epochs > 1000:
            raise ValueError(f"Epochs cannot exceed 1000, got {epochs}")
        
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
        
        results = self.model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            name=name,
            device=self.device,
            **kwargs
        )
        # Export the best model to ONNX for faster inference
        best_model_path = str(results.save_dir / "weights" / "best.pt")
        try:
            best_model = YOLO(best_model_path)
            best_model.export(format="onnx")
        except Exception as e:
            # Non-fatal if export fails
            print(f"ONNX export failed: {e}")
            pass
            
        return {
            "success": True,
            "epochs_completed": epochs,
            "model_path": best_model_path,
            "results_dir": str(results.save_dir),
            "metrics": {
                "map50": float(results.results_dict.get("metrics/mAP50(B)", 0)),
                "map50-95": float(results.results_dict.get("metrics/mAP50-95(B)", 0)),
            }
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

