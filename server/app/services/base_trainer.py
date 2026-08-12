"""
Abstract base class for model training backends.

All trainer implementations (YOLO, RT-DETR, TorchVision) must implement
this interface so that the training API endpoint can use them interchangeably.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable


class BaseTrainer(ABC):
    """Abstract interface for a detection model trainer."""

    @abstractmethod
    def train(
        self,
        data_config: str,
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        name: str = "train_run",
        project: str = "runs/detect",
        exist_ok: bool = True,
        strict_epochs: bool = False,
        augmentations: Optional[dict] = None,
        epoch_callback: Optional[Callable] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Train the model on the given dataset.

        Args:
            data_config: Path to dataset config (YOLO YAML or COCO JSON depending on backend).
            epochs: Number of training epochs.
            imgsz: Input image size.
            batch: Batch size.
            name: Run name (used for output directory).
            project: Project directory for saving results.
            exist_ok: If True, allow overwriting existing run directory.
            strict_epochs: If True, disable early stopping.
            augmentations: Dict of augmentation parameters.
            epoch_callback: Called after each epoch with (epoch, total_epochs, metrics_dict).
            **kwargs: Backend-specific extra parameters.

        Returns:
            Dict with standardized keys:
            {
                "success": bool,
                "epochs_completed": int,
                "model_path": str,       # path to best weights
                "results_dir": str,      # path to run output directory
                "metrics": {
                    "map50": float,
                    "map50-95": float,
                    "precision": float,
                    "recall": float,
                },
                "per_class_metrics": [
                    {"class_id": int, "class_name": str, "precision": float,
                     "recall": float, "mAP50": float, "mAP50_95": float}
                ],
                "confusion_matrix_path": Optional[str],
            }
        """
        pass

    @abstractmethod
    def validate(self, data_config: str) -> Dict[str, Any]:
        """Run validation on a dataset. Returns metrics dict."""
        pass

    @abstractmethod
    def export(self, format: str = "onnx") -> str:
        """Export the model to the specified format. Returns path to exported model."""
        pass
