import os
import zipfile
import tempfile
import uuid
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
from app.services.database import DatasetService, AnnotationService
from PIL import Image as PILImage

class DatasetImporter:
    """Service to import COCO/YOLO format datasets from a zip file."""

    @staticmethod
    def import_zip(dataset_id: str, zip_path: str, format_type: str) -> Dict:
        """
        Extracts zip, parses annotations, saves images, and writes to database.
        format_type must be 'yolo' or 'coco'
        """
        db_dataset = DatasetService.get_dataset(dataset_id)
        if not db_dataset:
            raise ValueError("Dataset not found")
        
        classes = db_dataset.get("classes", [])
        if not classes:
            raise ValueError("Dataset must have classes defined before importing")

        dataset_dir = Path(f"datasets/{dataset_id}/images")
        dataset_dir.mkdir(parents=True, exist_ok=True)
        
        extracted_images = 0
        extracted_annotations = 0
        errors = []

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
            except Exception as e:
                return {"success": False, "detail": f"Failed to extract zip: {str(e)}"}
            
            tmp_path = Path(tmpdir)

            # Find all images
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
            all_images = [p for p in tmp_path.rglob('*') if p.is_file() and p.suffix.lower() in image_extensions]

            if not all_images:
                return {"success": False, "detail": "No valid images found in the zip file"}

            if format_type.lower() == 'coco':
                results = DatasetImporter._import_coco(dataset_id, dataset_dir, all_images, tmp_path, classes)
            elif format_type.lower() == 'yolo':
                results = DatasetImporter._import_yolo(dataset_id, dataset_dir, all_images, tmp_path, classes)
            else:
                return {"success": False, "detail": f"Unsupported format type: {format_type}"}

            return results

    @staticmethod
    def _import_coco(dataset_id: str, dest_dir: Path, images: List[Path], root_dir: Path, dataset_classes: List[str]) -> Dict:
        # Find COCO json files
        json_files = list(root_dir.rglob('*.json'))
        if not json_files:
            return {"success": False, "detail": "COCO format selected but no JSON files found in zip"}
        
        # Parse all jsons (often there's one per split like _annotations.coco.json, train.json, etc)
        coco_data_list = []
        for jf in json_files:
            try:
                with open(jf, 'r') as f:
                    data = json.load(f)
                    if 'images' in data and 'annotations' in data:
                        coco_data_list.append(data)
            except:
                pass
        
        if not coco_data_list:
            return {"success": False, "detail": "Found JSON files, but none were valid COCO annotation formats"}

        total_images_saved = 0
        total_boxes_saved = 0

        # Build map of filename to image path
        img_name_to_path = {img.name: img for img in images}

        for coco_data in coco_data_list:
            categories = {cat['id']: cat['name'] for cat in coco_data.get('categories', [])}
            
            # Map COCO categories to Dataset classes
            # If COCO category name matches exactly, use that class_id, else assign to 0 or drop.
            cat_to_class_id = {}
            for cat_id, cat_name in categories.items():
                if cat_name in dataset_classes:
                    cat_to_class_id[cat_id] = dataset_classes.index(cat_name)
                else:
                    cat_to_class_id[cat_id] = -1 # Unmapped
            
            # Group annotations by image_id
            ann_by_image = {}
            for ann in coco_data.get('annotations', []):
                img_id = ann['image_id']
                if img_id not in ann_by_image:
                    ann_by_image[img_id] = []
                ann_by_image[img_id].append(ann)

            for img_info in coco_data.get('images', []):
                file_name = img_info['file_name'].split('/')[-1] # Handle nested paths in json
                if file_name not in img_name_to_path:
                    continue
                
                src_path = img_name_to_path[file_name]
                img_w = img_info.get('width')
                img_h = img_info.get('height')

                if not img_w or not img_h:
                    try:
                        with PILImage.open(src_path) as pil_img:
                            img_w, img_h = pil_img.size
                    except:
                        continue

                new_id = str(uuid.uuid4())
                new_filename = f"{new_id}{src_path.suffix.lower()}"
                dest_path = dest_dir / new_filename

                shutil.copy2(src_path, dest_path)
                
                DatasetService.add_image(
                    dataset_id=dataset_id,
                    image_id=new_id,
                    filename=new_filename,
                    original_name=file_name,
                    path=str(dest_path)
                )
                total_images_saved += 1

                boxes = []
                for ann in ann_by_image.get(img_info['id'], []):
                    cat_id = ann.get('category_id')
                    class_id = cat_to_class_id.get(cat_id, -1)
                    if class_id == -1:
                        continue # Skip unmapped classes
                    
                    bbox = ann.get('bbox') # [x_min, y_min, width, height]
                    if not bbox or len(bbox) != 4:
                        continue

                    boxes.append({
                        "x": float(bbox[0]),
                        "y": float(bbox[1]),
                        "width": float(bbox[2]),
                        "height": float(bbox[3]),
                        "class_id": class_id,
                        "class_name": dataset_classes[class_id]
                    })
                
                if boxes:
                    ann_payload = {
                        "image_id": new_id,
                        "image_name": new_filename,
                        "width": img_w,
                        "height": img_h,
                        "boxes": boxes
                    }
                    AnnotationService.save_annotation(dataset_id, new_id, ann_payload)
                    total_boxes_saved += len(boxes)
                    DatasetService.update_image_status(dataset_id, new_id, "annotated")

        return {
            "success": True,
            "images_imported": total_images_saved,
            "annotations_imported": total_boxes_saved
        }

    @staticmethod
    def _import_yolo(dataset_id: str, dest_dir: Path, images: List[Path], root_dir: Path, dataset_classes: List[str]) -> Dict:
        # Find YOLO txt files
        txt_files = {p.stem: p for p in root_dir.rglob('*.txt') if p.name != 'classes.txt'}
        
        total_images_saved = 0
        total_boxes_saved = 0

        for src_path in images:
            stem = src_path.stem
            
            try:
                with PILImage.open(src_path) as pil_img:
                    img_w, img_h = pil_img.size
            except:
                continue

            new_id = str(uuid.uuid4())
            new_filename = f"{new_id}{src_path.suffix.lower()}"
            dest_path = dest_dir / new_filename

            shutil.copy2(src_path, dest_path)
            
            DatasetService.add_image(
                dataset_id=dataset_id,
                image_id=new_id,
                filename=new_filename,
                original_name=src_path.name,
                path=str(dest_path)
            )
            total_images_saved += 1

            boxes = []
            if stem in txt_files:
                txt_path = txt_files[stem]
                try:
                    with open(txt_path, 'r') as f:
                        for line in f:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                class_id = int(parts[0])
                                # Standard YOLO: x_center, y_center, width, height (normalized)
                                cx, cy, w, h = map(float, parts[1:5])
                                
                                if class_id >= len(dataset_classes):
                                    continue # Skip if class ID doesn't exist in our project
                                
                                # Convert normalized YOLO back to absolute (x_min, y_min)
                                abs_w = w * img_w
                                abs_h = h * img_h
                                abs_x = (cx * img_w) - (abs_w / 2)
                                abs_y = (cy * img_h) - (abs_h / 2)

                                boxes.append({
                                    "x": float(abs_x),
                                    "y": float(abs_y),
                                    "width": float(abs_w),
                                    "height": float(abs_h),
                                    "class_id": class_id,
                                    "class_name": dataset_classes[class_id]
                                })
                except:
                    pass

            if boxes:
                ann_payload = {
                    "image_id": new_id,
                    "image_name": new_filename,
                    "width": img_w,
                    "height": img_h,
                    "boxes": boxes
                }
                AnnotationService.save_annotation(dataset_id, new_id, ann_payload)
                total_boxes_saved += len(boxes)
                DatasetService.update_image_status(dataset_id, new_id, "annotated")

        return {
            "success": True,
            "images_imported": total_images_saved,
            "annotations_imported": total_boxes_saved
        }
