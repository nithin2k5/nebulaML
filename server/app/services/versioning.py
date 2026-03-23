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
            
        # Optional Augmentations
        if augmentations.get("blur", False):
            transforms.append(A.Blur(blur_limit=3, p=0.5))
        if augmentations.get("flip", False):
            transforms.append(A.HorizontalFlip(p=0.5))
        if augmentations.get("rotate", False):
            transforms.append(A.Rotate(limit=15, p=0.5))
        if augmentations.get("brightness", False):
            transforms.append(A.RandomBrightnessContrast(p=0.5))
        if augmentations.get("noise", False):
            transforms.append(A.GaussNoise(p=0.5))
            
        return A.Compose(transforms, bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))

    def generate_version(self, dataset_id: str, name: str, preprocessing: Dict, augmentations: Dict, split_ratio: Dict = None) -> Optional[str]:
        """
        Takes the base dataset, applies preprocessing and augmentations, 
        and saves an immutable YOLO-format folder for training.
        """
        if split_ratio is None:
            split_ratio = {"train": 0.8, "val": 0.1, "test": 0.1}
            
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset: return None
        
        # Ensure there are annotated images before generating
        annotated_images = [img for img in dataset.get('images', []) if img.get('annotated')]
        if not annotated_images:
            raise ValueError("No annotated images found in the dataset. Please annotate some images before generating a version.")
        
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
        
        # Simple random split logic for now
        np.random.shuffle(images)
        n_train = int(len(images) * split_ratio['train'])
        n_val = int(len(images) * split_ratio['val'])
        
        splits = ['train'] * n_train + ['val'] * n_val + ['test'] * (len(images) - n_train - n_val)
        
        for img_data, split in zip(images, splits):
            # Only process annotated images
            if not img_data['annotated']: continue
                
            orig_path = img_data['path']
            annotation = AnnotationService.get_annotation(dataset_id, img_data['id'])
            if not annotation: continue
            
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
                    
                # Calculate normalized YOLO format coordinates
                center_x = (box.get("x", 0) + box.get("width", 0) / 2) / img_w
                center_y = (box.get("y", 0) + box.get("height", 0) / 2) / img_h
                norm_width = box.get("width", 0) / img_w
                norm_height = box.get("height", 0) / img_h
                
                # Clamp values to valid Albumentations [0, 1] bounds, ensuring width/height > 0
                center_x = max(0.0, min(1.0, center_x))
                center_y = max(0.0, min(1.0, center_y))
                norm_width = max(0.001, min(1.0, norm_width))
                norm_height = max(0.001, min(1.0, norm_height))
                
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
                with open(out_lbl_path, 'w') as f:
                    for bbox, label in zip(processed_bboxes, processed_labels):
                        f.write(f"{label} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}\n")
                        db_boxes.append({
                            "class_id": label,
                            "bbox_normalized": [bbox[0], bbox[1], bbox[2], bbox[3]]
                        })
                
                # Store Processed Image record in immutable DB snapshot
                unique_img_id = str(uuid.uuid4())
                DatasetVersionService.add_version_image(
                    unique_img_id, version_id, img_data['id'], 
                    out_img_name, str(out_img_path), 
                    w, h, split, db_boxes
                )
                        
            except Exception as e:
                print(f"Error processing image {img_data['id']}: {e}")
                continue

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
            'names': {i: name for i, name in enumerate(classes)}
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
        except:
            pass
        finally:
            if conn: conn.close()

        return version_id
