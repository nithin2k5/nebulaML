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

from app.services.base_trainer import BaseTrainer, TrainerState, TrainingCancelledException
from app.services.dataset_converter import yolo_yaml_to_coco_json
from app.services.detection_metrics import evaluate_detections

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


class _COCOValDataset(Dataset):
    """Validation view of a COCO split.

    Unlike the training dataset this keeps the original image size and absolute
    xyxy ground-truth boxes, which post-processing needs to map predictions back
    into image coordinates.
    """

    def __init__(self, json_path: str, processor):
        with open(json_path, "r") as f:
            coco = json.load(f)
        self.processor = processor
        self.images = {img["id"]: img for img in coco["images"]}
        self.ann_by_img = {}
        for ann in coco["annotations"]:
            self.ann_by_img.setdefault(ann["image_id"], []).append(ann)
        self.image_ids = list(self.images.keys())

    def __len__(self):
        return len(self.image_ids)

    def __getitem__(self, idx):
        img_id = self.image_ids[idx]
        img_info = self.images[img_id]
        image = Image.open(img_info["file_name"]).convert("RGB")

        encoding = self.processor(images=image, return_tensors="pt")

        boxes, labels = [], []
        for ann in self.ann_by_img.get(img_id, []):
            x, y, w, h = ann["bbox"]
            boxes.append([x, y, x + w, y + h])
            labels.append(ann["category_id"])

        return {
            "pixel_values": encoding["pixel_values"].squeeze(0),
            "size": (img_info["height"], img_info["width"]),
            "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor(labels, dtype=torch.int64).reshape(-1),
        }


def _collate_val(batch):
    return {
        "pixel_values": torch.stack([b["pixel_values"] for b in batch]),
        "sizes": [b["size"] for b in batch],
        "targets": [{"boxes": b["boxes"], "labels": b["labels"]} for b in batch],
    }


class RTDetrTrainer(BaseTrainer):
    """Fine-tune RT-DETR via HuggingFace transformers."""

    def __init__(self, checkpoint: str = "PekingU/rtdetr_r50vd"):
        self.checkpoint = checkpoint
        self.device = _get_device()
        self.model = None
        self.processor = None

    @staticmethod
    @torch.no_grad()
    def _evaluate(model, processor, val_loader, device, class_names: Dict[int, str]) -> Dict[str, Any]:
        """Run the model over the validation split and return COCO-style metrics."""
        was_training = model.training
        model.eval()

        predictions, targets = [], []
        for batch_data in val_loader:
            outputs = model(pixel_values=batch_data["pixel_values"].to(device))
            # A low threshold keeps the tail of the PR curve intact for AP.
            processed = processor.post_process_object_detection(
                outputs,
                threshold=0.001,
                target_sizes=torch.tensor(batch_data["sizes"], device=device),
            )
            for result, target in zip(processed, batch_data["targets"]):
                predictions.append({
                    "boxes": result["boxes"].detach().cpu().numpy(),
                    "scores": result["scores"].detach().cpu().numpy(),
                    "labels": result["labels"].detach().cpu().numpy(),
                })
                targets.append({
                    "boxes": target["boxes"].numpy(),
                    "labels": target["labels"].numpy(),
                })

        if was_training:
            model.train()
        return evaluate_detections(predictions, targets, class_names)

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

        # Callback support — the endpoint passes these to drive progress and cancellation
        epoch_end_cb = kwargs.pop("on_train_epoch_end", None)
        batch_end_cb = kwargs.pop("on_train_batch_end", None)
        job_info = kwargs.pop("job_info", None)
        if job_info is not None:
            job_info["device_used"] = str(device)

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
        self.model = model
        self.processor = processor
        self.device = device

        # 3. Dataset + DataLoader
        train_ds = _COCODataset(train_json, processor)
        train_loader = DataLoader(
            train_ds, batch_size=batch, shuffle=True,
            collate_fn=_collate, num_workers=0,
        )

        class_names = {c["id"]: c["name"] for c in categories}
        val_loader = None
        if "val" in coco_paths:
            val_ds = _COCOValDataset(coco_paths["val"], processor)
            if len(val_ds) > 0:
                val_loader = DataLoader(
                    val_ds, batch_size=batch, shuffle=False,
                    collate_fn=_collate_val, num_workers=0,
                )
        if val_loader is None:
            logger.warning(
                "No validation split available — checkpoint selection will fall back to "
                "training loss and reported metrics will be empty."
            )

        # 4. Optimizer
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(lr))

        # Prepare output directory
        run_dir = Path(project) / name
        weights_dir = run_dir / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        best_pt = weights_dir / "best.pt"

        best_loss = float("inf")
        best_map = -1.0
        best_eval: Dict[str, Any] = {}

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

                # Lets a cancel request take effect mid-epoch rather than waiting
                # for the epoch (and its validation pass) to finish.
                if batch_end_cb:
                    batch_end_cb(TrainerState(epoch=epoch - 1, epochs=epochs))

            avg_loss = epoch_loss / max(len(train_loader), 1)

            def _save_best():
                torch.save(model.state_dict(), best_pt)
                # Also save HF format for easy reloading
                hf_dir = weights_dir / "hf_model"
                model.save_pretrained(hf_dir)
                processor.save_pretrained(hf_dir)

            epoch_metrics = {"train/loss": avg_loss}
            if val_loader is not None:
                evaluation = self._evaluate(model, processor, val_loader, device, class_names)
                val_metrics = evaluation["metrics"]
                epoch_metrics.update({
                    "metrics/mAP50(B)": val_metrics["map50"],
                    "metrics/mAP50-95(B)": val_metrics["map50-95"],
                    "metrics/precision(B)": val_metrics["precision"],
                    "metrics/recall(B)": val_metrics["recall"],
                })
                # Select on validation mAP so the saved checkpoint is not just the
                # one that overfit the training split hardest.
                if val_metrics["map50-95"] > best_map:
                    best_map = val_metrics["map50-95"]
                    best_eval = evaluation
                    _save_best()
            elif avg_loss < best_loss:
                best_loss = avg_loss
                _save_best()

            # Epoch-end callback (mimics YOLO trainer_obj interface)
            if epoch_end_cb:
                obj = TrainerState(epoch=epoch - 1, epochs=epochs, metrics=epoch_metrics)
                try:
                    epoch_end_cb(obj)
                except TrainingCancelledException:
                    raise
                except Exception as cb_err:
                    logger.error("Epoch callback error: %s", cb_err)
                if obj.stop:
                    logger.info("Training cancelled by user at epoch %d", epoch)
                    break

            logger.info(
                "Epoch %d/%d — loss: %.4f, mAP50-95: %s",
                epoch, epochs, avg_loss,
                f"{epoch_metrics['metrics/mAP50-95(B)']:.4f}" if val_loader is not None else "n/a",
            )

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
            "metrics": best_eval.get("metrics", {
                "map50": 0.0,
                "map50-95": 0.0,
                "precision": 0.0,
                "recall": 0.0,
            }),
            "per_class_metrics": best_eval.get("per_class_metrics", []),
            "confusion_matrix_path": None,
        }

    def validate(self, data_config: str = "", **kwargs) -> Dict[str, Any]:
        """Evaluate the current model against the val split of a YOLO data.yaml."""
        if self.model is None or self.processor is None:
            raise RuntimeError("No trained model loaded — call train() first")

        coco_paths = yolo_yaml_to_coco_json(data_config)
        if "val" not in coco_paths:
            raise FileNotFoundError("Dataset has no validation split to evaluate against")

        with open(coco_paths["val"], "r") as f:
            categories = sorted(json.load(f)["categories"], key=lambda c: c["id"])
        class_names = {c["id"]: c["name"] for c in categories}

        val_loader = DataLoader(
            _COCOValDataset(coco_paths["val"], self.processor),
            batch_size=int(kwargs.get("batch", 4)), shuffle=False,
            collate_fn=_collate_val, num_workers=0,
        )
        return self._evaluate(self.model, self.processor, val_loader, self.device, class_names)

    def export(self, format: str = "onnx", **kwargs) -> str:
        return ""
