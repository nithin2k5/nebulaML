"""
Abstract base class for model inference backends.

All inference implementations must return detections in a standardized format.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseInference(ABC):
    """Abstract interface for a detection model inference engine."""

    @abstractmethod
    def predict(
        self,
        image: Any,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        augment: bool = False,
    ) -> List[Dict[str, Any]]:
        """Run inference on a single image.

        Args:
            image: PIL Image, numpy array, or file path.
            conf_threshold: Minimum confidence threshold.
            iou_threshold: IoU threshold for NMS.
            agnostic_nms: If True, class-agnostic NMS.
            augment: If True, use test-time augmentation.

        Returns:
            List of detection dicts, each with:
            {
                "class_id": int,
                "class_name": str,
                "confidence": float,
                "bbox": [x1, y1, x2, y2],            # absolute pixel coords
                "bbox_normalized": [cx, cy, w, h],     # normalized center format
            }
        """
        pass

    @abstractmethod
    def predict_batch(
        self,
        images: List[Any],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        augment: bool = False,
    ) -> List[List[Dict[str, Any]]]:
        """Run inference on multiple images. Returns list of detection lists."""
        pass
