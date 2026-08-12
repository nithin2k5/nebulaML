"""
Trainer factory — returns the correct trainer implementation based on model_name.
"""
from app.services.base_trainer import BaseTrainer
from app.services.model_registry import get_backend, get_model_info
import logging

logger = logging.getLogger(__name__)


def create_trainer(model_name: str) -> BaseTrainer:
    """Create and return the appropriate trainer for the given model.

    Args:
        model_name: A model key from the model registry.

    Returns:
        A BaseTrainer implementation.

    Raises:
        ValueError: If the model backend is unknown.
    """
    backend = get_backend(model_name)
    info = get_model_info(model_name)
    checkpoint = info.checkpoint if info else model_name

    logger.info("Creating trainer for model '%s' (backend=%s, checkpoint=%s)",
                model_name, backend, checkpoint)

    if backend == "yolo":
        from app.services.trainer import YOLOTrainer
        return YOLOTrainer(checkpoint)
    elif backend == "rtdetr":
        from app.services.rtdetr_trainer import RTDetrTrainer
        return RTDetrTrainer(checkpoint)
    elif backend == "torchvision":
        from app.services.torchvision_trainer import TorchVisionTrainer
        return TorchVisionTrainer(checkpoint, model_key=model_name)
    else:
        raise ValueError(f"Unknown model backend: {backend} for model {model_name}")


def create_inference(model_path: str, model_type: str = "yolo"):
    """Create and return the appropriate inference engine.

    Args:
        model_path: Path to the model weights file.
        model_type: Backend type ("yolo", "rtdetr", "torchvision").

    Returns:
        A BaseInference implementation.
    """
    logger.info("Creating inference engine (type=%s, path=%s)", model_type, model_path)

    if model_type == "yolo":
        from app.services.inference import YOLOInference
        return YOLOInference(model_path)
    elif model_type == "rtdetr":
        from app.services.rtdetr_inference import RTDetrInference
        return RTDetrInference(model_path)
    elif model_type == "torchvision":
        from app.services.torchvision_inference import TorchVisionInference
        return TorchVisionInference(model_path)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
