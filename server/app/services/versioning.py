import hashlib
import os
import json
import uuid
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import cv2
import numpy as np
import albumentations as A
import shutil

from app.services.database import DatasetService, DatasetVersionService, AnnotationService

class DatasetDriftError(Exception):
    def __init__(self, message: str, diff_summary: Dict[str, Any]):
        super().__init__(message)
        self.diff_summary = diff_summary

PREFLIGHT_TTL_SECONDS = 3600  # 1 hour

class VersioningEngine:
    """
    Engine to handle generation of Roboflow-style dataset versions,
    including preprocessing, augmentations, and generation of YOLO yaml configs.
    """
    
    def __init__(self):
        self.base_dir = Path("uploads/datasets")
        self.versions_dir = Path("uploads/versions")
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        
    def _build_augmentation_pipeline(self, preprocessing: Dict, augmentations: Dict) -> A.Compose:
        """Builds an Albumentations pipeline from requested config"""
        transforms = []
        
        # Preprocessing operations
        if "resize" in preprocessing:
            width, height = preprocessing["resize"].get("width", 640), preprocessing["resize"].get("height", 640)
            transforms.append(A.Resize(height=height, width=width))
            
        # Optional Augmentations — accepts both frontend keys and legacy keys
        if augmentations.get("blur", False):
            transforms.append(A.Blur(blur_limit=3, p=0.5))
        if augmentations.get("flipHorizontal", False) or augmentations.get("flip", False):
            transforms.append(A.HorizontalFlip(p=0.5))
        if augmentations.get("flipVertical", False):
            transforms.append(A.VerticalFlip(p=0.5))
        if augmentations.get("rotate", False):
            transforms.append(A.Rotate(limit=15, p=0.5))
        if augmentations.get("brightness", False):
            transforms.append(A.RandomBrightnessContrast(p=0.5))
        if augmentations.get("grayscale", False) or augmentations.get("noise", False):
            transforms.append(A.ToGray(p=0.5))
            
        return A.Compose(transforms, bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))

    def generate_version(self, dataset_id: str, name: str, preprocessing: Dict, augmentations: Dict, split_ratio: Dict = None, force: bool = False) -> Optional[str]:
        """
        Takes the base dataset, applies preprocessing and augmentations, 
        and saves an immutable YOLO-format folder for training.
        """
        from app.services.dataset_manifest import compute_manifest, PreflightResultService
        import datetime
        import logging
        logger = logging.getLogger(__name__)

        current_manifest = compute_manifest(dataset_id)
        last_result = PreflightResultService.get_latest(dataset_id)
        
        exported_without_current_preflight = False
        
        if not last_result:
            raise ValueError("No preflight on record, run preflight before exporting.")
            
        computed_at = datetime.datetime.fromisoformat(last_result.get("computed_at"))
        now = datetime.datetime.now()
        age_seconds = (now - computed_at).total_seconds()
        
        is_stale = age_seconds > PREFLIGHT_TTL_SECONDS
        is_drifted = last_result.get("manifest_hash") != current_manifest["manifest_hash"]
        
        if is_stale or is_drifted:
            if not force:
                diff_summary = {
                    "is_stale": is_stale,
                    "is_drifted": is_drifted,
                    "age_seconds": age_seconds,
                    "last_hash": last_result.get("manifest_hash"),
                    "current_hash": current_manifest["manifest_hash"]
                }
                msg = "Dataset drift detected: data has changed since last preflight." if is_drifted else "Preflight result is stale (older than 1 hour)."
                raise DatasetDriftError(msg, diff_summary)
            else:
                logger.warning(f"Forcing export for {dataset_id} despite drift/staleness.")
                exported_without_current_preflight = True

        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset: return None
        
        # Ensure there are annotated images before generating
        annotated_images = [img for img in dataset.get('images', []) if img.get('annotated')]
        if not annotated_images:
            raise ValueError("No annotated images found in the dataset. Please annotate some images before generating a version.")
        
        if exported_without_current_preflight:
            augmentations["_exported_without_current_preflight"] = True

        # 1. Register Version in DB
        versions_list = DatasetVersionService.list_dataset_versions(dataset_id)
        version_num = len(versions_list) + 1
        version_id = str(uuid.uuid4())
        
        DatasetVersionService.create_version(
            version_id=version_id, 
            dataset_id=dataset_id, 
            version_number=version_num, 
            name=name, 
            preprocessing=preprocessing, 
            augmentations=augmentations
        )
        
        # 2. Setup Version Output Directory (YOLO format)
        version_dir = self.versions_dir / version_id
        for split in ['train', 'val', 'test']:
            (version_dir / split / 'images').mkdir(parents=True, exist_ok=True)
            (version_dir / split / 'labels').mkdir(parents=True, exist_ok=True)
            
        # 3. Apply Transformations & Save
        pipeline = self._build_augmentation_pipeline(preprocessing, augmentations)
        images = dataset['images']
        
        images = list(images)
        # We now rely entirely on the DB's explicitly assigned splits
        splits = [img.get('split', 'train') for img in images]
        
        
        aug_data = {
            "corrupt_images": [],
            "annotations": {},
            "image_dims": {}
        }
        
        for img_data, split in zip(images, splits):
            # Only process images that are actually annotated
            if not img_data['annotated']: continue
                
            orig_path = img_data['path']
            annotation = AnnotationService.get_annotation(dataset_id, img_data['id'])
            if not annotation: continue

            # Skip images whose annotation has no bounding boxes — they produce empty YOLO labels
            if not annotation.get('boxes'):
                continue
            
            # Read image
            image = cv2.imread(orig_path)
            if image is None: continue
            
            # Prepare bounding boxes for Albumentations (YOLO format: x_center, y_center, width, height)
            bboxes = []
            class_labels = []
            
            for box in annotation['boxes']:
                img_w = annotation.get('width', 1)
                img_h = annotation.get('height', 1)
                
                if img_w <= 0 or img_h <= 0:
                    continue
                    
                # First calculate min/max coordinates
                x_min = box.get("x", 0) / img_w
                y_min = box.get("y", 0) / img_h
                x_max = (box.get("x", 0) + box.get("width", 0)) / img_w
                y_max = (box.get("y", 0) + box.get("height", 0)) / img_h
                
                # Clamp strict bounds [0, 1]
                x_min = max(0.0, min(1.0, x_min))
                y_min = max(0.0, min(1.0, y_min))
                x_max = max(0.0, min(1.0, x_max))
                y_max = max(0.0, min(1.0, y_max))
                
                # Re-calculate YOLO format
                norm_width = x_max - x_min
                norm_height = y_max - y_min
                center_x = x_min + (norm_width / 2.0)
                center_y = y_min + (norm_height / 2.0)
                
                # Skip invalid tiny boxes
                if norm_width < 0.001 or norm_height < 0.001:
                    continue
                
                bboxes.append([center_x, center_y, norm_width, norm_height])
                class_labels.append(box.get('class_id', 0))
                
            # Apply Transformation
            try:
                transformed = pipeline(image=image, bboxes=bboxes, class_labels=class_labels)
                processed_image = transformed['image']
                processed_bboxes = transformed['bboxes']
                processed_labels = transformed['class_labels']
                
                h, w = processed_image.shape[:2]
                
                # Save Image
                out_img_name = f"{img_data['id']}_{uuid.uuid4().hex[:6]}.jpg"
                out_img_path = version_dir / split / 'images' / out_img_name
                cv2.imwrite(str(out_img_path), processed_image)
                
                # Save YOLO Label TXT
                out_lbl_path = version_dir / split / 'labels' / out_img_name.replace('.jpg', '.txt')
                
                db_boxes = []
                # Reconstruct pixel coords for Stage A validation
                pixel_boxes = []
                with open(out_lbl_path, 'w') as f:
                    for bbox, label in zip(processed_bboxes, processed_labels):
                        f.write(f"{label} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}\n")
                        db_boxes.append({
                            "class_id": label,
                            "bbox_normalized": [bbox[0], bbox[1], bbox[2], bbox[3]]
                        })
                        # Convert YOLO normalized back to top-left pixel format
                        cx, cy, bw, bh = bbox[0], bbox[1], bbox[2], bbox[3]
                        px = (cx - bw / 2.0) * w
                        py = (cy - bh / 2.0) * h
                        pixel_boxes.append({
                            "x": px, "y": py, "width": bw * w, "height": bh * h
                        })
                
                # Store Processed Image record in immutable DB snapshot
                unique_img_id = str(uuid.uuid4())
                DatasetVersionService.add_version_image(
                    unique_img_id, version_id, img_data['id'], 
                    out_img_name, str(out_img_path), 
                    w, h, split, db_boxes
                )
                
                # Record for post-aug validation
                aug_data["image_dims"][unique_img_id] = (w, h)
                aug_data["annotations"][unique_img_id] = pixel_boxes
                        
            except Exception as e:
                print(f"Error processing image {img_data['id']}: {e}")
                continue

        # Post-augmentation re-validation (Stage A)
        from app.services.preflight import PreflightPipeline
        aug_reports = PreflightPipeline._stage_a_structural(aug_data)
        aug_blockers = [r for r in aug_reports if r['severity'] == 'blocking']
        if aug_blockers:
            raise DatasetDriftError("Post-augmentation structural validation failed (e.g., degenerate box created).", {"blockers": aug_blockers})

        # 4. Generate data.yaml for this specific version
        yaml_path = version_dir / 'data.yaml'
        classes = dataset['classes']
        
        val_has_images = len(list((version_dir / 'val' / 'images').glob('*.jpg'))) > 0
        test_has_images = len(list((version_dir / 'test' / 'images').glob('*.jpg'))) > 0
        
        yaml_data = {
            'path': str(version_dir.absolute()),
            'train': 'train/images',
            'val': 'val/images' if val_has_images else 'train/images',
            'test': 'test/images' if test_has_images else '',
            'names': {i: name for i, name in enumerate(classes)},
            'nc': len(classes)
        }
        
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, sort_keys=False)
            
        # Register yaml path
        from app.db.session import get_db_connection
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE dataset_versions SET yaml_path = %s WHERE id = %s", (str(yaml_path), version_id))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update yaml_path in DB for version {version_id}: {e}")
        finally:
            if conn: conn.close()

        return version_id
