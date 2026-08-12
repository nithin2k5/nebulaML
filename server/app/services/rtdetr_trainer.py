"""
RT-DETR Trainer — fine-tunes RT-DETR models from HuggingFace on custom datasets.

Accepts the same parameters as YOLOTrainer so the training endpoint can call
`trainer.train(**train_params)` interchangeably.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

import torch
from torch.utils.data import Dataset, DataLoader
from PIL import Image

from app.services.base_trainer import BaseTrainer
from app.services.dataset_converter import yolo_yaml_to_coco_json

logger = logging.getLogger(__name__)


def _get_device(requested=None):
    """Auto-detect best device: cuda → mps → cpu."""
    if requested and requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class _COCODataset(Dataset):
    """Simple COCO-format dataset for RT-DETR fine-tuning."""

    def __init__(self, json_path: str, processor):
        with open(json_path, "r") as f:
            self.coco = json.load(f)
        self.processor = processor
        self.images = {img["id"]: img for img in self.coco["images"]}
        # Group annotations by image_id
        self.ann_by_img = {}
        for ann in self.coco["annotations"]:
            self.ann_by_img.setdefault(ann["image_id"], []).append(ann)
        self.image_ids = list(self.images.keys())

    def __len__(self):
        return len(self.image_ids)

    def __getitem__(self, idx):
        img_id = self.image_ids[idx]
        img_info = self.images[img_id]
        image = Image.open(img_info["file_name"]).convert("RGB")

        anns = self.ann_by_img.get(img_id, [])
        target = {
            "image_id": img_id,
            "annotations": [
                {
                    "bbox": ann["bbox"],           # COCO [x,y,w,h]
                    "category_id": ann["category_id"],
                    "area": ann["area"],
                    "iscrowd": 0,
                    "image_id": img_id,
                    "id": ann["id"],
                }
                for ann in anns
            ],
        }

        encoding = self.processor(images=image, annotations=target, return_tensors="pt")
        # Squeeze the batch dimension the processor adds
        return {
            k: v.squeeze(0) if isinstance(v, torch.Tensor) else v
            for k, v in encoding.items()
        }


def _collate(batch):
    pixel_values = torch.stack([b["pixel_values"] for b in batch])
    labels = [b["labels"] for b in batch]
    return {"pixel_values": pixel_values, "labels": labels}


class RTDetrTrainer(BaseTrainer):
    """Fine-tune RT-DETR via HuggingFace transformers."""

    def __init__(self, checkpoint: str = "PekingU/rtdetr_r50vd"):
        self.checkpoint = checkpoint
        self.device = _get_device()

    # ── Accept the same **kwargs that run_training() passes ───────────
    def train(
        self,
        data_yaml: str = "",          # path to YOLO data.yaml
        epochs: int = 50,
        imgsz: int = 640,
        batch: int = 4,
        name: str = "rtdetr_run",
        project: str = "runs/detect",
        exist_ok: bool = True,
        strict_epochs: bool = False,
        augmentations: Optional[dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Train RT-DETR. Converts YOLO YAML → COCO JSON internally."""

        try:
            from transformers import RTDetrForObjectDetection, RTDetrImageProcessor
        except ImportError as e:
            raise RuntimeError(
                "RT-DETR requires the 'transformers' package. "
                "Install with: pip install transformers>=4.40.0"
            ) from e

        lr = kwargs.pop("lr0", 5e-5)
        device_req = kwargs.pop("device", None)
        device = _get_device(device_req) if device_req else self.device

        # Callback support — the endpoint passes on_train_epoch_end
        epoch_end_cb = kwargs.pop("on_train_epoch_end", None)

        logger.info("RT-DETR training: checkpoint=%s, epochs=%d, lr=%s, device=%s",
                     self.checkpoint, epochs, lr, device)

        # 1. Convert YOLO dataset to COCO JSON
        coco_paths = yolo_yaml_to_coco_json(data_yaml)
        if "train" not in coco_paths:
            raise FileNotFoundError("COCO conversion produced no training split")
        train_json = coco_paths["train"]

        # Read class info from generated JSON
        with open(train_json, "r") as f:
            coco_data = json.load(f)
        categories = sorted(coco_data["categories"], key=lambda c: c["id"])
        id2label = {c["id"]: c["name"] for c in categories}
        label2id = {c["name"]: c["id"] for c in categories}
        num_classes = len(categories)

        # 2. Load processor + model
        processor = RTDetrImageProcessor.from_pretrained(self.checkpoint)
        model = RTDetrForObjectDetection.from_pretrained(
            self.checkpoint,
            num_labels=num_classes,
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True,
        )
        model.to(device)

        # 3. Dataset + DataLoader
        train_ds = _COCODataset(train_json, processor)
        train_loader = DataLoader(
            train_ds, batch_size=batch, shuffle=True,
            collate_fn=_collate, num_workers=0,
        )

        # 4. Optimizer
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(lr))

        # Prepare output directory
        run_dir = Path(project) / name
        weights_dir = run_dir / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        best_pt = weights_dir / "best.pt"

        best_loss = float("inf")

        # 5. Training loop
        model.train()
        for epoch in range(1, epochs + 1):
            epoch_loss = 0.0
            for step, batch_data in enumerate(train_loader):
                pixel_values = batch_data["pixel_values"].to(device)
                labels = [
                    {k: v.to(device) for k, v in t.items()} for t in batch_data["labels"]
                ]
                outputs = model(pixel_values=pixel_values, labels=labels)
                loss = outputs.loss

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / max(len(train_loader), 1)

            if avg_loss < best_loss:
                best_loss = avg_loss
                torch.save(model.state_dict(), best_pt)
                # Also save HF format for easy reloading
                hf_dir = weights_dir / "hf_model"
                model.save_pretrained(hf_dir)
                processor.save_pretrained(hf_dir)

            # Epoch-end callback (mimics YOLO trainer_obj interface)
            if epoch_end_cb:
                class _FakeTrainerObj:
                    pass
                obj = _FakeTrainerObj()
                obj.epoch = epoch - 1   # 0-indexed like YOLO
                obj.epochs = epochs
                obj.metrics = {"train/loss": avg_loss}
                obj.stop = False
                try:
                    epoch_end_cb(obj)
                    if obj.stop:
                        logger.info("Training cancelled by user at epoch %d", epoch)
                        break
                except Exception as cb_err:
                    logger.error("Epoch callback error: %s", cb_err)

            logger.info("Epoch %d/%d — loss: %.4f", epoch, epochs, avg_loss)

        # 6. Save model_meta.json
        meta = {
            "backend": "rtdetr",
            "checkpoint": self.checkpoint,
            "num_classes": num_classes,
            "class_names": [c["name"] for c in categories],
        }
        with open(run_dir / "model_meta.json", "w") as f:
            json.dump(meta, f)

        # 7. Return standardized result
        return {
            "success": True,
            "epochs_completed": epoch,
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
