"""
RT-DETR Inference — runs inference using a fine-tuned RT-DETR model.

Matches the BaseInference interface so it can be used interchangeably
with YOLOInference.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

import torch
from PIL import Image
import numpy as np

try:
    from transformers import RTDetrForObjectDetection, RTDetrImageProcessor
except ImportError:
    logging.warning("transformers not installed. RT-DETR inference will not work.")

from app.services.base_inference import BaseInference

logger = logging.getLogger(__name__)


def _get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class RTDetrInference(BaseInference):
    """RT-DETR inference engine using HuggingFace transformers."""

    def __init__(self, model_path: str):
        self.device = _get_device()
        model_path = Path(model_path)

        # Resolve the run directory from the weights path
        if model_path.is_file():
            # e.g. .../job_xxx/weights/best.pt  →  .../job_xxx
            run_dir = model_path.parent.parent
        elif model_path.name == "model_meta.json":
            run_dir = model_path.parent
        else:
            run_dir = model_path

        hf_dir = run_dir / "weights" / "hf_model"
        meta_path = run_dir / "model_meta.json"

        if not meta_path.exists():
            raise FileNotFoundError(f"model_meta.json not found at {meta_path}")

        with open(meta_path, "r") as f:
            self.meta = json.load(f)

        self.class_names = self.meta.get("class_names", [])

        self.processor = RTDetrImageProcessor.from_pretrained(str(hf_dir))
        self.model = RTDetrForObjectDetection.from_pretrained(str(hf_dir))
        self.model.to(self.device)
        self.model.eval()

    def _to_pil(self, image) -> Image.Image:
        """Convert various image types to PIL Image."""
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        if isinstance(image, np.ndarray):
            return Image.fromarray(image).convert("RGB")
        if isinstance(image, str) or isinstance(image, Path):
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

        inputs = self.processor(images=pil_image, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        results = self.processor.post_process_object_detection(
            outputs,
            target_sizes=torch.tensor([(height, width)]),
            threshold=conf_threshold,
        )[0]

        detections = []
        for score, label_id, box in zip(results["scores"], results["labels"], results["boxes"]):
            x1, y1, x2, y2 = box.tolist()
            cls_id = label_id.item()
            cls_name = self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id)

            # Normalized center format
            cx = ((x1 + x2) / 2) / width
            cy = ((y1 + y2) / 2) / height
            bw = (x2 - x1) / width
            bh = (y2 - y1) / height

            detections.append({
                "class_id": cls_id,
                "class_name": cls_name,
                "confidence": round(score.item(), 4),
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
