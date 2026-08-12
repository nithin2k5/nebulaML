"""
TorchVision Inference — runs inference using fine-tuned TorchVision detection models.

Matches the BaseInference interface so it can be used interchangeably
with YOLOInference.
"""
import json
import logging
import math
from pathlib import Path
from typing import List, Dict, Any

import torch
import numpy as np
from PIL import Image

try:
    import torchvision
    from torchvision.models.detection import (
        fasterrcnn_resnet50_fpn_v2,
        fasterrcnn_mobilenet_v3_large_fpn,
        fcos_resnet50_fpn,
        retinanet_resnet50_fpn_v2,
        ssd300_vgg16,
        ssdlite320_mobilenet_v3_large,
    )
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    from torchvision.transforms import v2 as T
except ImportError:
    logging.warning("torchvision not installed. TorchVisionInference will not work.")

from app.services.base_inference import BaseInference

logger = logging.getLogger(__name__)


def _get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class TorchVisionInference(BaseInference):
    """TorchVision detection inference engine."""

    def __init__(self, model_path: str):
        self.device = _get_device()
        model_path = Path(model_path)

        # Resolve run directory
        if model_path.is_file() and model_path.suffix == ".pt":
            run_dir = model_path.parent.parent
            weights_path = model_path
        elif model_path.name == "model_meta.json":
            run_dir = model_path.parent
            weights_path = run_dir / "weights" / "best.pt"
        else:
            run_dir = model_path
            weights_path = run_dir / "weights" / "best.pt"

        meta_path = run_dir / "model_meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"model_meta.json not found at {meta_path}")

        with open(meta_path, "r") as f:
            self.meta = json.load(f)

        self.class_names = self.meta.get("class_names", [])
        self.num_classes = self.meta.get("num_classes", len(self.class_names))
        self.checkpoint = self.meta.get("checkpoint", "fasterrcnn_resnet50_fpn_v2")

        # Build model architecture and load weights
        self.model = self._build_model(self.num_classes)
        self.model.load_state_dict(
            torch.load(str(weights_path), map_location=self.device, weights_only=True)
        )
        self.model.to(self.device)
        self.model.eval()

        self.transforms = T.Compose([T.ToImage(), T.ToDtype(torch.float32, scale=True)])

    def _build_model(self, num_classes: int):
        """Reconstruct the model architecture (no pretrained weights)."""
        if "fasterrcnn_mobilenet" in self.checkpoint:
            model = fasterrcnn_mobilenet_v3_large_fpn(weights=None)
            in_features = model.roi_heads.box_predictor.cls_score.in_features
            model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
        elif "fasterrcnn" in self.checkpoint:
            model = fasterrcnn_resnet50_fpn_v2(weights=None)
            in_features = model.roi_heads.box_predictor.cls_score.in_features
            model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
        elif "fcos" in self.checkpoint:
            model = fcos_resnet50_fpn(weights=None, num_classes=num_classes)
        elif "retinanet" in self.checkpoint:
            model = retinanet_resnet50_fpn_v2(weights=None, num_classes=num_classes)
        elif "ssdlite" in self.checkpoint:
            model = ssdlite320_mobilenet_v3_large(weights=None, num_classes=num_classes)
        elif "ssd" in self.checkpoint:
            model = ssd300_vgg16(weights=None, num_classes=num_classes)
        else:
            model = fasterrcnn_resnet50_fpn_v2(weights=None)
            in_features = model.roi_heads.box_predictor.cls_score.in_features
            model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
        return model

    def _to_pil(self, image) -> Image.Image:
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        if isinstance(image, np.ndarray):
            return Image.fromarray(image).convert("RGB")
        if isinstance(image, (str, Path)):
            return Image.open(image).convert("RGB")
        return image

    def predict(
        self,
        image: Any,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        augment: bool = False,
    ) -> List[Dict[str, Any]]:
        """Run inference on a single image."""
        pil_image = self._to_pil(image)
        width, height = pil_image.size

        img_tensor = self.transforms(pil_image).to(self.device)

        with torch.no_grad():
            outputs = self.model([img_tensor])

        preds = outputs[0]
        detections = []

        for i in range(len(preds["boxes"])):
            score = preds["scores"][i].item()
            if score < conf_threshold:
                continue

            x1, y1, x2, y2 = preds["boxes"][i].tolist()
            label = preds["labels"][i].item()
            cls_name = self.class_names[label] if label < len(self.class_names) else str(label)

            cx = ((x1 + x2) / 2) / width
            cy = ((y1 + y2) / 2) / height
            bw = (x2 - x1) / width
            bh = (y2 - y1) / height

            detections.append({
                "class_id": label,
                "class_name": cls_name,
                "confidence": round(score, 4),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "bbox_normalized": [round(cx, 6), round(cy, 6), round(bw, 6), round(bh, 6)],
            })

        return detections

    def predict_batch(
        self,
        images: List[Any],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        augment: bool = False,
    ) -> List[List[Dict[str, Any]]]:
        """Run inference on multiple images."""
        return [
            self.predict(img, conf_threshold, iou_threshold, agnostic_nms, augment)
            for img in images
        ]
