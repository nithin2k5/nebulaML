"""
Dataset Builder Module for YOLO Format Conversion

This module handles:
- Reading images from database or storage folder
- Reading bounding boxes from CRUD records
- Converting to YOLO label format
- Train/val split (80/20)
- Creating folder structure
- Generating data.yaml
- Label validation
- Safe handling of missing files
"""

import json
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import yaml


def _valid_yolo_label_parts(parts: List[str]) -> bool:
    n = len(parts)
    if n == 0:
        return True
    if n == 1:
        try:
            int(parts[0])
            return True
        except ValueError:
            return False
    if n == 5:
        try:
            int(parts[0])
            vals = [float(p) for p in parts[1:]]
            return all(0 <= v <= 1 for v in vals)
        except ValueError:
            return False
    if n >= 7 and n % 2 == 1:
        try:
            int(parts[0])
            for i in range(1, n):
                v = float(parts[i])
                if not 0 <= v <= 1:
                    return False
            return True
        except ValueError:
            return False
    return False


@dataclass
class BoundingBox:
    """Represents a bounding box annotation."""
    class_id: int
    x_center: float  # Normalized (0-1)
    y_center: float  # Normalized (0-1)
    width: float     # Normalized (0-1)
    height: float    # Normalized (0-1)

    def to_yolo_line(self) -> str:
        """Convert to YOLO format line: class_id x_center y_center width height"""
        return f"{self.class_id} {self.x_center:.6f} {self.y_center:.6f} {self.width:.6f} {self.height:.6f}"

    @classmethod
    def from_absolute(cls, class_id: int, x_min: float, y_min: float, x_max: float, y_max: float, 
                     img_width: int, img_height: int) -> 'BoundingBox':
        """Create from absolute coordinates."""
        # Normalize coordinates
        x_center = ((x_min + x_max) / 2.0) / img_width
        y_center = ((y_min + y_max) / 2.0) / img_height
        width = (x_max - x_min) / img_width
        height = (y_max - y_min) / img_height
        
        # Validate normalized coordinates
        x_center = max(0.0, min(1.0, x_center))
        y_center = max(0.0, min(1.0, y_center))
        width = max(0.0, min(1.0, width))
        height = max(0.0, min(1.0, height))
        
        return cls(class_id=class_id, x_center=x_center, y_center=y_center, width=width, height=height)

    @classmethod
    def from_normalized(cls, class_id: int, x_center: float, y_center: float, 
                       width: float, height: float) -> 'BoundingBox':
        """Create from normalized coordinates."""
        # Validate
        x_center = max(0.0, min(1.0, x_center))
        y_center = max(0.0, min(1.0, y_center))
        width = max(0.0, min(1.0, width))
        height = max(0.0, min(1.0, height))
        
        return cls(class_id=class_id, x_center=x_center, y_center=y_center, width=width, height=height)

    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate bounding box coordinates."""
        if not (0 <= self.x_center <= 1):
            return False, f"x_center {self.x_center} out of range [0, 1]"
        if not (0 <= self.y_center <= 1):
            return False, f"y_center {self.y_center} out of range [0, 1]"
        if not (0 <= self.width <= 1):
            return False, f"width {self.width} out of range [0, 1]"
        if not (0 <= self.height <= 1):
            return False, f"height {self.height} out of range [0, 1]"
        if self.width <= 0 or self.height <= 0:
            return False, "width or height is zero or negative"
        
        # Check if box extends beyond image boundaries
        if self.x_center - self.width / 2 < 0 or self.x_center + self.width / 2 > 1:
            return False, "box extends beyond x boundaries"
        if self.y_center - self.height / 2 < 0 or self.y_center + self.height / 2 > 1:
            return False, "box extends beyond y boundaries"
        
        return True, None


@dataclass
class ImageAnnotation:
    """Represents an image with its annotations."""
    image_path: Union[str, Path]
    image_id: Optional[str] = None
    bounding_boxes: List[BoundingBox] = field(default_factory=list)
    width: Optional[int] = None
    height: Optional[int] = None

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate image annotation."""
        errors = []
        
        # Check if image file exists
        img_path = Path(self.image_path)
        if not img_path.exists():
            errors.append(f"Image file not found: {self.image_path}")
            return False, errors
        
        # Validate each bounding box
        for i, bbox in enumerate(self.bounding_boxes):
            is_valid, error_msg = bbox.validate()
            if not is_valid:
                errors.append(f"Bounding box {i}: {error_msg}")
        
        return len(errors) == 0, errors


class DatasetBuilder:
    """Builds YOLO-format datasets from images and annotations."""
    
    def __init__(self, output_dir: Union[str, Path], class_names: List[str], 
                 train_ratio: float = 0.8, random_seed: Optional[int] = None):
        """
        Initialize dataset builder.
        
        Args:
            output_dir: Root directory for dataset output
            class_names: List of class names (e.g., ['person', 'car', 'bike'])
            train_ratio: Ratio of training data (default: 0.8)
            random_seed: Random seed for reproducibility
        """
        self.output_dir = Path(output_dir)
        self.class_names = class_names
        self.num_classes = len(class_names)
        self.train_ratio = train_ratio
        self.val_ratio = 1.0 - train_ratio
        
        if random_seed is not None:
            random.seed(random_seed)
        
        # Create directory structure
        self.train_images_dir = self.output_dir / "images" / "train"
        self.val_images_dir = self.output_dir / "images" / "val"
        self.train_labels_dir = self.output_dir / "labels" / "train"
        self.val_labels_dir = self.output_dir / "labels" / "val"
        
        self._create_directories()
    
    def _create_directories(self):
        """Create the required directory structure."""
        self.train_images_dir.mkdir(parents=True, exist_ok=True)
        self.val_images_dir.mkdir(parents=True, exist_ok=True)
        self.train_labels_dir.mkdir(parents=True, exist_ok=True)
        self.val_labels_dir.mkdir(parents=True, exist_ok=True)
    
    def build_from_annotations(self, annotations: List[ImageAnnotation], 
                              copy_images: bool = True) -> Dict[str, any]:
        """
        Build dataset from list of image annotations.
        
        Args:
            annotations: List of ImageAnnotation objects
            copy_images: If True, copy images; if False, create symlinks
        
        Returns:
            Dictionary with build statistics
        """
        # Validate all annotations first
        valid_annotations = []
        invalid_count = 0
        
        for ann in annotations:
            is_valid, errors = ann.validate()
            if is_valid:
                valid_annotations.append(ann)
            else:
                invalid_count += 1
                print(f"Warning: Skipping invalid annotation for {ann.image_path}: {', '.join(errors)}")
        
        if len(valid_annotations) == 0:
            raise ValueError("No valid annotations found")
        
        # Shuffle for random split
        random.shuffle(valid_annotations)
        
        # Split into train/val
        split_idx = int(len(valid_annotations) * self.train_ratio)
        train_annotations = valid_annotations[:split_idx]
        val_annotations = valid_annotations[split_idx:]
        
        # Process training set
        train_stats = self._process_split(train_annotations, self.train_images_dir, 
                                         self.train_labels_dir, copy_images, "train")
        
        # Process validation set
        val_stats = self._process_split(val_annotations, self.val_images_dir, 
                                       self.val_labels_dir, copy_images, "val")
        
        # Generate data.yaml
        yaml_path = self.output_dir / "data.yaml"
        self._generate_yaml(yaml_path)
        
        return {
            "total_annotations": len(annotations),
            "valid_annotations": len(valid_annotations),
            "invalid_annotations": invalid_count,
            "train": train_stats,
            "val": val_stats,
            "yaml_path": str(yaml_path)
        }
    
    def build_from_database(self, db_connection, query: str, 
                           image_base_path: Union[str, Path],
                           copy_images: bool = True) -> Dict[str, any]:
        """
        Build dataset from database records.
        
        Args:
            db_connection: Database connection object (must have execute/fetchall methods)
            query: SQL query that returns (image_id, image_path, annotations_json, width, height)
                  annotations_json should be a JSON array of [class_id, x_min, y_min, x_max, y_max]
            image_base_path: Base path for images
            copy_images: If True, copy images; if False, create symlinks
        
        Returns:
            Dictionary with build statistics
        """
        image_base_path = Path(image_base_path)
        annotations = []
        
        # Execute query and process results
        cursor = db_connection.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            image_id, image_path, annotations_json, width, height = row
            
            # Construct full image path
            full_image_path = image_base_path / image_path if not Path(image_path).is_absolute() else Path(image_path)
            
            # Parse annotations
            bboxes = []
            if annotations_json:
                try:
                    ann_data = json.loads(annotations_json) if isinstance(annotations_json, str) else annotations_json
                    for ann in ann_data:
                        if len(ann) >= 5:
                            class_id, x_min, y_min, x_max, y_max = ann[:5]
                            bbox = BoundingBox.from_absolute(
                                class_id, x_min, y_min, x_max, y_max, width or 640, height or 640
                            )
                            bboxes.append(bbox)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"Warning: Failed to parse annotations for {image_id}: {e}")
                    continue
            
            ann_obj = ImageAnnotation(
                image_path=full_image_path,
                image_id=str(image_id),
                bounding_boxes=bboxes,
                width=width,
                height=height
            )
            annotations.append(ann_obj)
        
        return self.build_from_annotations(annotations, copy_images)
    
    def build_from_folder(self, images_folder: Union[str, Path], 
                         annotations_file: Optional[Union[str, Path]] = None,
                         annotations_dict: Optional[Dict[str, List[Dict]]] = None,
                         copy_images: bool = True) -> Dict[str, any]:
        """
        Build dataset from folder of images and annotations file/dict.
        
        Args:
            images_folder: Folder containing images
            annotations_file: JSON file mapping image_name -> annotations
            annotations_dict: Dictionary mapping image_name -> annotations
            copy_images: If True, copy images; if False, create symlinks
        
        Returns:
            Dictionary with build statistics
        """
        images_folder = Path(images_folder)
        if not images_folder.exists():
            raise ValueError(f"Images folder not found: {images_folder}")
        
        # Load annotations
        if annotations_file:
            with open(annotations_file, 'r') as f:
                annotations_dict = json.load(f)
        elif not annotations_dict:
            raise ValueError("Either annotations_file or annotations_dict must be provided")
        
        # Supported image extensions
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
        
        annotations = []
        for image_path in images_folder.iterdir():
            if image_path.suffix.lower() not in image_extensions:
                continue
            
            image_name = image_path.name
            image_anns = annotations_dict.get(image_name, [])
            
            # Convert annotations to BoundingBox objects
            bboxes = []
            for ann in image_anns:
                # Support multiple formats
                if isinstance(ann, dict):
                    # Format: {"class_id": 0, "x_center": 0.5, "y_center": 0.5, "width": 0.1, "height": 0.1}
                    if "x_center" in ann:
                        bbox = BoundingBox.from_normalized(
                            ann["class_id"], ann["x_center"], ann["y_center"],
                            ann["width"], ann["height"]
                        )
                    # Format: {"class_id": 0, "x_min": 100, "y_min": 100, "x_max": 200, "y_max": 200}
                    elif "x_min" in ann:
                        # Try to get image dimensions
                        from PIL import Image
                        try:
                            img = Image.open(image_path)
                            width, height = img.size
                        except Exception:
                            width, height = 640, 640  # Default
                        
                        bbox = BoundingBox.from_absolute(
                            ann["class_id"], ann["x_min"], ann["y_min"],
                            ann["x_max"], ann["y_max"], width, height
                        )
                    else:
                        continue
                elif isinstance(ann, list) and len(ann) >= 5:
                    # Format: [class_id, x_min, y_min, x_max, y_max] or [class_id, x_center, y_center, width, height]
                    # Try normalized first, then absolute
                    try:
                        from PIL import Image
                        img = Image.open(image_path)
                        width, height = img.size
                    except Exception:
                        width, height = 640, 640
                    
                    # Check if values are normalized (0-1) or absolute
                    if all(0 <= v <= 1 for v in ann[1:5]):
                        bbox = BoundingBox.from_normalized(ann[0], ann[1], ann[2], ann[3], ann[4])
                    else:
                        bbox = BoundingBox.from_absolute(ann[0], ann[1], ann[2], ann[3], ann[4], width, height)
                else:
                    continue
                
                bboxes.append(bbox)
            
            ann_obj = ImageAnnotation(
                image_path=image_path,
                image_id=image_name,
                bounding_boxes=bboxes
            )
            annotations.append(ann_obj)
        
        return self.build_from_annotations(annotations, copy_images)
    
    def _process_split(self, annotations: List[ImageAnnotation], 
                      images_dir: Path, labels_dir: Path,
                      copy_images: bool, split_name: str) -> Dict[str, any]:
        """Process a split (train or val) of annotations."""
        processed = 0
        skipped = 0
        total_boxes = 0
        
        for ann in annotations:
            try:
                source_path = Path(ann.image_path)
                if not source_path.exists():
                    skipped += 1
                    continue
                
                # Get image filename
                image_filename = source_path.name
                label_filename = source_path.stem + ".txt"
                
                # Copy or link image
                dest_image_path = images_dir / image_filename
                if copy_images:
                    shutil.copy2(source_path, dest_image_path)
                else:
                    if dest_image_path.exists():
                        dest_image_path.unlink()
                    dest_image_path.symlink_to(source_path.absolute())
                
                # Write label file
                label_path = labels_dir / label_filename
                with open(label_path, 'w') as f:
                    for bbox in ann.bounding_boxes:
                        f.write(bbox.to_yolo_line() + "\n")
                        total_boxes += 1
                
                processed += 1
            except Exception as e:
                print(f"Error processing {ann.image_path} for {split_name}: {e}")
                skipped += 1
        
        return {
            "images": processed,
            "skipped": skipped,
            "total_boxes": total_boxes
        }
    
    def _generate_yaml(self, yaml_path: Path):
        """Generate data.yaml file for YOLO training."""
        yaml_data = {
            "path": str(self.output_dir.absolute()),
            "train": "images/train",
            "val": "images/val",
            "nc": self.num_classes,
            "names": self.class_names
        }
        
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)
    
    def validate_dataset(self) -> Dict[str, any]:
        """
        Validate the created dataset.
        
        Returns:
            Dictionary with validation results
        """
        issues = []
        stats = {
            "train_images": 0,
            "train_labels": 0,
            "val_images": 0,
            "val_labels": 0,
            "missing_labels": [],
            "missing_images": [],
            "invalid_labels": []
        }
        
        # Check train set
        for img_path in self.train_images_dir.iterdir():
            if img_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}:
                stats["train_images"] += 1
                label_path = self.train_labels_dir / (img_path.stem + ".txt")
                if not label_path.exists():
                    stats["missing_labels"].append(str(img_path))
                    issues.append(f"Missing label for train image: {img_path.name}")
        
        for label_path in self.train_labels_dir.iterdir():
            if label_path.suffix == '.txt':
                stats["train_labels"] += 1
                img_path = self.train_images_dir / (label_path.stem + ".jpg")
                if not img_path.exists():
                    img_path = self.train_images_dir / (label_path.stem + ".png")
                if not img_path.exists():
                    stats["missing_images"].append(str(label_path))
                    issues.append(f"Missing image for train label: {label_path.name}")
                
                # Validate label format
                try:
                    with open(label_path, 'r') as f:
                        for line_num, line in enumerate(f, 1):
                            parts = line.strip().split()
                            if not parts:
                                continue
                            if not _valid_yolo_label_parts(parts):
                                stats["invalid_labels"].append(f"{label_path.name}:{line_num}")
                                issues.append(f"Invalid label format in {label_path.name} line {line_num}")
                                continue
                            try:
                                if len(parts) > 1:
                                    values = [float(x) for x in parts[1:]]
                                    if not all(0 <= v <= 1 for v in values):
                                        stats["invalid_labels"].append(f"{label_path.name}:{line_num}")
                                        issues.append(f"Values out of range in {label_path.name} line {line_num}")
                            except ValueError:
                                stats["invalid_labels"].append(f"{label_path.name}:{line_num}")
                                issues.append(f"Non-numeric values in {label_path.name} line {line_num}")
                except Exception as e:
                    issues.append(f"Error reading {label_path}: {e}")
        
        # Check val set
        for img_path in self.val_images_dir.iterdir():
            if img_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}:
                stats["val_images"] += 1
                label_path = self.val_labels_dir / (img_path.stem + ".txt")
                if not label_path.exists():
                    stats["missing_labels"].append(str(img_path))
                    issues.append(f"Missing label for val image: {img_path.name}")
        
        for label_path in self.val_labels_dir.iterdir():
            if label_path.suffix == '.txt':
                stats["val_labels"] += 1
                img_path = self.val_images_dir / (label_path.stem + ".jpg")
                if not img_path.exists():
                    img_path = self.val_images_dir / (label_path.stem + ".png")
                if not img_path.exists():
                    stats["missing_images"].append(str(label_path))
                    issues.append(f"Missing image for val label: {label_path.name}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "stats": stats
        }
