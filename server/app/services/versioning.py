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
from app.services import segmentation_labels as seglabels
import logging

logger = logging.getLogger(__name__)

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
        
    def _build_augmentation_pipeline(
        self, preprocessing: Dict, augmentations: Dict, task: str = "detect"
    ) -> A.Compose:
        """Builds an Albumentations pipeline from requested config.

        A segmentation version transforms polygon *vertices*, so the pipeline
        is declared with keypoint params instead of bbox params. The transforms
        themselves are identical — what differs is what albumentations is asked
        to carry through them.
        """
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
            
        if task == "segment":
            # remove_invisible=False keeps a vertex that a rotation pushed off
            # the canvas, so the polygon survives with its shape intact and is
            # clamped back to the frame on the way out. Dropping it instead
            # would silently deform the mask.
            return A.Compose(
                transforms,
                keypoint_params=A.KeypointParams(
                    format='xy',
                    label_fields=['kp_instance'],
                    remove_invisible=False,
                ),
            )

        return A.Compose(transforms, bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))

    def generate_version(self, dataset_id: str, name: str, preprocessing: Dict, augmentations: Dict, split_ratio: Dict = None, force: bool = False, task: str = "detect") -> Optional[str]:
        """
        Takes the base dataset, applies preprocessing and augmentations,
        and saves an immutable YOLO-format folder for training.

        `task` fixes what the label files contain: "detect" writes one
        `class cx cy w h` line per instance, "segment" writes
        `class x1 y1 x2 y2 …` polygons. It is recorded on the version because
        a run has to be refused if its model trains the other one — a
        segmentation checkpoint pointed at box labels does not error, it just
        learns rectangles and reports metrics that look fine.
        """
        if task not in ("detect", "segment"):
            raise ValueError(f"Unsupported task '{task}' (expected 'detect' or 'segment')")
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

        if task == "segment":
            # Boxes do become 4-point polygons below, so a segment version is
            # technically producible from a box-only dataset — but it would
            # train masks that are all rectangles, which is worse than
            # detection at the same cost. Refuse it rather than let someone
            # discover that from the metrics.
            all_annotations = AnnotationService.get_all_dataset_annotations(dataset_id)
            polygon_count = seglabels.count_polygon_instances(all_annotations)
            if polygon_count == 0:
                raise ValueError(
                    "This dataset has no polygon annotations, so a segmentation "
                    "version would contain nothing but rectangular masks. Draw "
                    "polygons in the annotator, or generate a detection version."
                )
            logger.info(
                "Generating segment version for %s from %d polygon instances",
                dataset_id, polygon_count,
            )
        
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
            augmentations=augmentations,
            task=task
        )
        
        # 2. Setup Version Output Directory (YOLO format)
        version_dir = self.versions_dir / version_id
        for split in ['train', 'val', 'test']:
            (version_dir / split / 'images').mkdir(parents=True, exist_ok=True)
            (version_dir / split / 'labels').mkdir(parents=True, exist_ok=True)
            
        # 3. Apply Transformations & Save
        pipeline = self._build_augmentation_pipeline(preprocessing, augmentations, task)
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
            
            img_w = annotation.get('width', 1)
            img_h = annotation.get('height', 1)
            if img_w <= 0 or img_h <= 0:
                continue

            # Prepare the instances for Albumentations. Detection carries
            # boxes in YOLO format; segmentation carries polygon vertices as
            # keypoints, since that is the only way albumentations will apply
            # a geometric transform to a shape with more than four corners.
            bboxes = []
            class_labels = []
            instances = []

            if task == "segment":
                for box in annotation['boxes']:
                    polygon = seglabels.instance_polygon(box, img_w, img_h)
                    if polygon is None:
                        continue
                    instances.append((int(box.get('class_id', 0)), polygon))
                if not instances:
                    continue
            else:
                for box in annotation['boxes']:
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
                if task == "segment":
                    # Vertices go in as pixels against the image actually on
                    # disk, not the dimensions recorded on the annotation, so
                    # a row whose stored size drifted cannot shift the mask.
                    in_h, in_w = image.shape[:2]
                    keypoints = []
                    kp_instance = []
                    for idx, (_cid, polygon) in enumerate(instances):
                        for nx, ny in polygon:
                            keypoints.append((nx * in_w, ny * in_h))
                            kp_instance.append(idx)

                    transformed = pipeline(
                        image=image, keypoints=keypoints, kp_instance=kp_instance
                    )
                    processed_image = transformed['image']
                    h, w = processed_image.shape[:2]

                    # Regroup by instance label rather than by original order:
                    # a transform is free to reorder what it returns.
                    regrouped = {}
                    for (kx, ky), idx in zip(
                        transformed['keypoints'], transformed['kp_instance']
                    ):
                        regrouped.setdefault(int(idx), []).append(
                            (float(kx) / w, float(ky) / h)
                        )

                    processed_instances = []
                    for idx, (class_id, _original) in enumerate(instances):
                        points = regrouped.get(idx) or []
                        if len(points) < 3:
                            continue
                        clamped = [
                            (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))
                            for x, y in points
                        ]
                        bx, by, bw, bh = seglabels.polygon_bbox(clamped)
                        if bw < seglabels.MIN_EXTENT or bh < seglabels.MIN_EXTENT:
                            # The transform flattened it out of the frame.
                            continue
                        processed_instances.append((class_id, clamped, (bx, by, bw, bh)))

                    if not processed_instances:
                        continue
                else:
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
                    if task == "segment":
                        for class_id, points, (bx, by, bw, bh) in processed_instances:
                            f.write(seglabels.format_segment_line(class_id, points) + "\n")
                            # The snapshot keeps a box alongside the polygon:
                            # preflight and the evaluation workbench both read
                            # boxes, and deriving it here means the two cannot
                            # drift apart.
                            db_boxes.append({
                                "class_id": class_id,
                                "bbox_normalized": [bx + bw / 2.0, by + bh / 2.0, bw, bh],
                                "polygon_normalized": [coord for p in points for coord in p],
                            })
                            pixel_boxes.append({
                                "x": bx * w, "y": by * h, "width": bw * w, "height": bh * h
                            })
                    else:
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
                logger.error(f"Error processing image {img_data['id']}: {e}")
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
