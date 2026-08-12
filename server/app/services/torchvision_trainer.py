"""
TorchVision Trainer — fine-tunes Faster R-CNN, FCOS, RetinaNet, SSD on custom datasets.

Accepts the same parameters as YOLOTrainer so the training endpoint can call
`trainer.train(**train_params)` interchangeably.
"""
import json
import logging
import math
from pathlib import Path
from typing import Dict, Any, Optional

import torch
from torch.utils.data import Dataset, DataLoader
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
    logging.warning("torchvision not installed. TorchVisionTrainer will not work.")

from app.services.base_trainer import BaseTrainer
from app.services.dataset_converter import yolo_yaml_to_coco_json

logger = logging.getLogger(__name__)


def _get_device(requested=None):
    if requested and requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class _COCODataset(Dataset):
    """Minimal COCO dataset for TorchVision detection models."""

    def __init__(self, json_path: str, transforms=None):
        with open(json_path, "r") as f:
            self.coco = json.load(f)
        self.images = {img["id"]: img for img in self.coco["images"]}
        self.ann_by_img = {}
        for ann in self.coco["annotations"]:
            self.ann_by_img.setdefault(ann["image_id"], []).append(ann)
        self.image_ids = list(self.images.keys())
        self.transforms = transforms

    def __len__(self):
        return len(self.image_ids)

    def __getitem__(self, idx):
        img_id = self.image_ids[idx]
        img_info = self.images[img_id]
        image = Image.open(img_info["file_name"]).convert("RGB")

        anns = self.ann_by_img.get(img_id, [])
        boxes, labels = [], []
        for ann in anns:
            x, y, w, h = ann["bbox"]
            boxes.append([x, y, x + w, y + h])
            # TorchVision expects 1-indexed labels (0 = background)
            labels.append(ann["category_id"] + 1)

        if boxes:
            boxes = torch.as_tensor(boxes, dtype=torch.float32)
            labels = torch.as_tensor(labels, dtype=torch.int64)
        else:
            boxes = torch.empty((0, 4), dtype=torch.float32)
            labels = torch.empty((0,), dtype=torch.int64)

        target = {
            "boxes": boxes,
            "labels": labels,
            "image_id": torch.tensor([img_id]),
        }

        if self.transforms is not None:
            image, target = self.transforms(image, target)

        return image, target


def _get_transforms():
    return T.Compose([T.ToImage(), T.ToDtype(torch.float32, scale=True)])


def _collate(batch):
    return tuple(zip(*batch))


# ── Model loader map ────────────────────────────────────────────────
_MODEL_LOADERS = {
    "fasterrcnn_resnet50_fpn_v2": fasterrcnn_resnet50_fpn_v2,
    "fasterrcnn_mobilenet_v3_large_fpn": fasterrcnn_mobilenet_v3_large_fpn,
    "fcos_resnet50_fpn": fcos_resnet50_fpn,
    "retinanet_resnet50_fpn_v2": retinanet_resnet50_fpn_v2,
    "ssd300_vgg16": ssd300_vgg16,
    "ssdlite320_mobilenet_v3_large": ssdlite320_mobilenet_v3_large,
}


class TorchVisionTrainer(BaseTrainer):
    """Fine-tune TorchVision detection models."""

    def __init__(self, checkpoint: str = "fasterrcnn_resnet50_fpn_v2", model_key: str = ""):
        self.checkpoint = checkpoint
        self.model_key = model_key
        self.device = _get_device()

    def _build_model(self, num_classes: int):
        """Load pretrained model and replace the classification head."""
        loader = _MODEL_LOADERS.get(self.checkpoint)
        if loader is None:
            logger.warning("Unknown checkpoint '%s', falling back to Faster R-CNN", self.checkpoint)
            loader = fasterrcnn_resnet50_fpn_v2

        model = loader(weights="DEFAULT")

        # Replace head for custom class count
        if "fasterrcnn" in self.checkpoint:
            in_features = model.roi_heads.box_predictor.cls_score.in_features
            model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
        elif "fcos" in self.checkpoint:
            num_anchors = model.head.classification_head.num_anchors
            out_channels = model.head.classification_head.conv[-3].out_channels  # last Conv2d in the stack
            model.head.classification_head.num_classes = num_classes
            cls_logits = torch.nn.Conv2d(out_channels, num_anchors * num_classes, 3, padding=1)
            torch.nn.init.normal_(cls_logits.weight, std=0.01)
            torch.nn.init.constant_(cls_logits.bias, -math.log((1 - 0.01) / 0.01))
            model.head.classification_head.cls_logits = cls_logits
        elif "retinanet" in self.checkpoint:
            in_channels = model.head.classification_head.conv[0].in_channels
            num_anchors = model.head.classification_head.num_anchors
            model.head.classification_head.num_classes = num_classes
            cls_logits = torch.nn.Conv2d(in_channels, num_anchors * num_classes, 3, padding=1)
            torch.nn.init.normal_(cls_logits.weight, std=0.01)
            torch.nn.init.constant_(cls_logits.bias, -math.log((1 - 0.01) / 0.01))
            model.head.classification_head.cls_logits = cls_logits
        # SSD / SSDLite — head replacement is more involved; use as-is for COCO 91 classes
        # or skip custom training for SSD (inference-only with pretrained weights)

        return model

    # ── Accept the same **kwargs that run_training() passes ──────────
    def train(
        self,
        data_yaml: str = "",
        epochs: int = 50,
        imgsz: int = 800,
        batch: int = 4,
        name: str = "tv_run",
        project: str = "runs/detect",
        exist_ok: bool = True,
        strict_epochs: bool = False,
        augmentations: Optional[dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Train a TorchVision detection model. Converts YOLO YAML → COCO JSON internally."""

        lr = float(kwargs.pop("lr0", 0.005))
        device_req = kwargs.pop("device", None)
        device = _get_device(device_req) if device_req else self.device
        epoch_end_cb = kwargs.pop("on_train_epoch_end", None)

        logger.info("TorchVision training: model=%s, epochs=%d, lr=%s, device=%s",
                     self.checkpoint, epochs, lr, device)

        # 1. Convert YOLO → COCO
        coco_paths = yolo_yaml_to_coco_json(data_yaml)
        if "train" not in coco_paths:
            raise FileNotFoundError("COCO conversion produced no training split")
        train_json = coco_paths["train"]

        with open(train_json, "r") as f:
            coco_data = json.load(f)

        categories = sorted(coco_data["categories"], key=lambda c: c["id"])
        num_classes = len(categories) + 1  # +1 for background

        # 2. Model
        model = self._build_model(num_classes)
        model.to(device)

        # 3. Dataset + DataLoader
        train_ds = _COCODataset(train_json, transforms=_get_transforms())
        train_loader = DataLoader(
            train_ds, batch_size=batch, shuffle=True,
            collate_fn=_collate, num_workers=0,
        )

        # 4. Optimizer
        params = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.SGD(params, lr=lr, momentum=0.9, weight_decay=0.0005)
        lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=max(epochs // 3, 1), gamma=0.1)

        # Output directory
        run_dir = Path(project) / name
        weights_dir = run_dir / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        best_pt = weights_dir / "best.pt"

        best_loss = float("inf")
        completed_epoch = 0

        # 5. Training loop
        for epoch in range(1, epochs + 1):
            model.train()
            epoch_loss = 0.0
            for images, targets in train_loader:
                images = [img.to(device) for img in images]
                targets = [{k: v.to(device) for k, v in t.items()} for t in targets]

                loss_dict = model(images, targets)
                losses = sum(loss for loss in loss_dict.values())

                optimizer.zero_grad()
                losses.backward()
                optimizer.step()
                epoch_loss += losses.item()

            lr_scheduler.step()
            avg_loss = epoch_loss / max(len(train_loader), 1)
            completed_epoch = epoch

            if avg_loss < best_loss:
                best_loss = avg_loss
                torch.save(model.state_dict(), best_pt)

            # Epoch-end callback (same fake trainer_obj as RT-DETR)
            if epoch_end_cb:
                class _Obj:
                    pass
                obj = _Obj()
                obj.epoch = epoch - 1
                obj.epochs = epochs
                obj.metrics = {"train/loss": avg_loss}
                obj.stop = False
                try:
                    epoch_end_cb(obj)
                    if obj.stop:
                        logger.info("Training cancelled at epoch %d", epoch)
                        break
                except Exception as cb_err:
                    logger.error("Epoch callback error: %s", cb_err)

            logger.info("Epoch %d/%d — loss: %.4f", epoch, epochs, avg_loss)

        # 6. model_meta.json
        meta = {
            "backend": "torchvision",
            "checkpoint": self.checkpoint,
            "model_key": self.model_key,
            "num_classes": num_classes,
            "class_names": ["__background__"] + [c["name"] for c in categories],
        }
        with open(run_dir / "model_meta.json", "w") as f:
            json.dump(meta, f)

        return {
            "success": True,
            "epochs_completed": completed_epoch,
            "model_path": str(best_pt),
            "results_dir": str(run_dir),
            "metrics": {
                "map50": 0.0,
                "map50-95": 0.0,
                "precision": 0.0,
                "recall": 0.0,
            },
            "per_class_metrics": [],
            "confusion_matrix_path": None,
        }

    def validate(self, data_config: str = "", **kwargs) -> Dict[str, Any]:
        return {"metrics": {}}

    def export(self, format: str = "onnx", **kwargs) -> str:
        return ""
