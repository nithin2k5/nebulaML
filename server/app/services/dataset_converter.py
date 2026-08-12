"""
Dataset format converter: YOLO ↔ COCO.

YOLO format: text files with `class_id center_x center_y width height` (normalized)
COCO format: JSON with images, annotations, categories arrays

Used by RT-DETR and TorchVision trainers which expect COCO-style data.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image as PILImage
import logging

logger = logging.getLogger(__name__)


def yolo_yaml_to_coco_json(
    data_yaml_path: str,
    output_dir: Optional[str] = None,
) -> Dict[str, str]:
    """Convert a YOLO-format dataset (referenced by data.yaml) to COCO JSON.

    Reads the YAML, finds train/val image+label dirs, and produces
    `train_coco.json` and `val_coco.json` in the output directory.

    Args:
        data_yaml_path: Path to the YOLO data.yaml file.
        output_dir: Where to write the COCO JSONs. Defaults to same dir as YAML.

    Returns:
        Dict with keys 'train' and 'val' pointing to the generated JSON paths.
    """
    import yaml

    with open(data_yaml_path, "r") as f:
        data = yaml.safe_load(f)

    base_path = Path(data.get("path", Path(data_yaml_path).parent))
    if not base_path.is_absolute():
        base_path = Path(data_yaml_path).parent / base_path

    class_names = data.get("names", [])
    if isinstance(class_names, dict):
        # Handle {0: 'class0', 1: 'class1'} format
        max_id = max(class_names.keys())
        class_names = [class_names.get(i, f"class_{i}") for i in range(max_id + 1)]

    out_dir = Path(output_dir) if output_dir else base_path
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {}
    for split in ("train", "val"):
        split_rel = data.get(split, f"{split}/images")
        images_dir = (base_path / split_rel).resolve()
        # Labels dir mirrors images dir with 'labels' instead of 'images'
        labels_dir = Path(str(images_dir).replace("/images", "/labels"))

        if not images_dir.exists():
            logger.warning("Images dir not found for split '%s': %s", split, images_dir)
            continue

        coco = _convert_split(images_dir, labels_dir, class_names)
        out_path = out_dir / f"{split}_coco.json"
        with open(out_path, "w") as f:
            json.dump(coco, f)
        result[split] = str(out_path)
        logger.info("Wrote COCO JSON for '%s' → %s (%d images, %d annotations)",
                    split, out_path, len(coco["images"]), len(coco["annotations"]))

    return result


def _convert_split(
    images_dir: Path,
    labels_dir: Path,
    class_names: List[str],
) -> dict:
    """Convert one split (train or val) from YOLO to COCO format."""
    IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

    categories = [
        {"id": i, "name": name, "supercategory": "object"}
        for i, name in enumerate(class_names)
    ]

    images = []
    annotations = []
    ann_id = 1

    image_files = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in IMG_EXTS
    )

    for img_id, img_path in enumerate(image_files, start=1):
        try:
            with PILImage.open(img_path) as img:
                w, h = img.size
        except Exception:
            logger.warning("Could not read image %s, skipping", img_path)
            continue

        images.append({
            "id": img_id,
            "file_name": str(img_path),  # absolute path for loader
            "width": w,
            "height": h,
        })

        label_path = labels_dir / (img_path.stem + ".txt")
        if not label_path.exists():
            continue

        with open(label_path, "r") as lf:
            for line in lf:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                cls_id = int(parts[0])
                cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])

                # Convert YOLO normalized (cx, cy, w, h) → COCO absolute (x, y, w, h)
                abs_w = bw * w
                abs_h = bh * h
                abs_x = (cx * w) - (abs_w / 2)
                abs_y = (cy * h) - (abs_h / 2)

                annotations.append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cls_id,
                    "bbox": [abs_x, abs_y, abs_w, abs_h],  # COCO format
                    "area": abs_w * abs_h,
                    "iscrowd": 0,
                })
                ann_id += 1

    return {
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }
