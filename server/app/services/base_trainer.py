"""
Abstract base class for model training backends.

All trainer implementations (YOLO, RT-DETR, TorchVision) must implement
this interface so that the training API endpoint can use them interchangeably.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable


class TrainingCancelledException(Exception):
    """Raised from a training callback when the user has requested cancellation.

    Lives here rather than in a single backend so every trainer can let it
    propagate out of train() instead of swallowing it as a generic callback error.
    """


def set_seed(seed: int, deterministic: bool = False) -> None:
    """Seed Python, numpy and torch RNGs so a run can be reproduced.

    The hand-rolled backends need this explicitly; ultralytics seeds itself from
    the `seed` argument.
    """
    import random

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    if deterministic:
        # warn_only: some detection ops have no deterministic kernel, and failing
        # the run over that is worse than a slightly non-reproducible op.
        torch.use_deterministic_algorithms(True, warn_only=True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


class TrainerState:
    """Stand-in for the ultralytics trainer object that callbacks expect.

    The training endpoint's callbacks are written against ultralytics' interface,
    so the hand-rolled backends pass one of these to stay compatible.
    """

    def __init__(self, epoch: int = 0, epochs: int = 0, metrics: Optional[dict] = None):
        self.epoch = epoch
        self.epochs = epochs
        self.metrics = metrics or {}
        self.stop = False


class BaseTrainer(ABC):
    """Abstract interface for a detection model trainer."""

    @abstractmethod
    def train(
        self,
        data_yaml: str,
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        name: str = "train_run",
        project: str = "runs/detect",
        exist_ok: bool = True,
        strict_epochs: bool = False,
        augmentations: Optional[dict] = None,
        on_train_epoch_end: Optional[Callable] = None,
        on_train_batch_end: Optional[Callable] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Train the model on the given dataset.

        Args:
            data_yaml: Path to the YOLO dataset YAML. Backends that need COCO
                convert it internally.
            epochs: Number of training epochs.
            imgsz: Input image size.
            batch: Batch size.
            name: Run name (used for output directory).
            project: Project directory for saving results.
            exist_ok: If True, allow overwriting existing run directory.
            strict_epochs: If True, disable early stopping.
            augmentations: Dict of augmentation parameters.
            on_train_epoch_end: Called after each epoch with a TrainerState. May raise
                TrainingCancelledException, which implementations must let propagate.
            on_train_batch_end: Same contract, called after each batch.
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
    def validate(self, data_yaml: str) -> Dict[str, Any]:
        """Run validation on a dataset. Returns metrics dict."""
        pass

    @abstractmethod
    def export(self, format: str = "onnx") -> str:
        """Export the model to the specified format. Returns path to exported model."""
        pass
