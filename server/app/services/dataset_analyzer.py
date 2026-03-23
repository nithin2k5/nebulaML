"""
Comprehensive Dataset Analysis Service for YOLO Training

Provides analysis for:
- Dataset structure validation
- Quality metrics
- Class distribution
- Object size/aspect ratio analysis
- Data validation
- Training recommendations
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter, defaultdict
from PIL import Image
import hashlib
from dataclasses import dataclass, asdict
import yaml

# Optional numpy import
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    # Fallback for numpy operations
    def mean(values):
        return sum(values) / len(values) if values else 0.0
    
    def std(values):
        if not values:
            return 0.0
        m = mean(values)
        variance = sum((x - m) ** 2 for x in values) / len(values)
        return variance ** 0.5

from app.services.database import DatasetService, AnnotationService

logger = logging.getLogger(__name__)


@dataclass
class DatasetAnalysis:
    """Comprehensive dataset analysis results"""
    dataset_id: str
    dataset_name: str
    
    # Basic stats
    total_images: int
    annotated_images: int
    total_annotations: int
    classes: List[str]
    
    # Class distribution
    class_frequency: Dict[str, int]
    class_balance_score: float  # 0-1, higher is better
    
    # Object size analysis
    object_size_distribution: Dict[str, int]  # tiny, small, medium, large
    aspect_ratio_distribution: Dict[str, int]
    avg_objects_per_image: float
    
    # Dataset structure
    structure_valid: bool
    structure_issues: List[str]
    
    # Quality metrics
    label_accuracy_score: float  # 0-1
    iou_consistency_score: float  # 0-1
    duplicate_images: List[str]
    corrupt_images: List[str]
    label_mismatches: List[str]
    invalid_boxes: List[str]
    empty_annotations: List[str]
    invalid_class_ids: List[str]
    boxes_out_of_bounds: List[str]
    
    # Split analysis
    split_distribution: Dict[str, int]
    split_ratios: Dict[str, float]
    data_leakage_detected: bool
    
    # Recommendations
    recommended_image_size: int
    recommended_batch_size: int
    recommended_epochs: int
    augmentation_recommendations: Dict[str, Any]
    
    # Overall quality
    overall_quality_score: float  # 0-100
    warnings: List[str]
    recommendations: List[str]


class DatasetAnalyzer:
    """Analyze datasets for training readiness"""
    
    # Size thresholds (relative to image)
    TINY_THRESHOLD = 0.01  # < 1% of image
    SMALL_THRESHOLD = 0.05  # < 5% of image
    MEDIUM_THRESHOLD = 0.2  # < 20% of image
    # LARGE = > 20%
    
    @staticmethod
    def analyze_dataset(dataset_id: str) -> DatasetAnalysis:
        """Perform comprehensive dataset analysis"""
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")
        
        images = DatasetService.get_dataset_images(dataset_id)
        annotated_images = [img for img in images if img.get("annotated", False)]
        
        # Get all annotations
        all_annotations = []
        class_counts = Counter()
        object_sizes = []
        aspect_ratios = []
        image_hashes = {}
        corrupt_images = []
        label_mismatches = []
        invalid_boxes = []
        empty_annotations = []
        invalid_class_ids = []
        boxes_out_of_bounds = []
        dataset_classes = dataset.get("classes", [])
        
        for img in annotated_images:
            annotation = AnnotationService.get_annotation(dataset_id, img["id"])
            if not annotation:
                empty_annotations.append(img["filename"])
                continue
            
            # Validate image file
            img_path = Path(img["path"])
            if not img_path.exists():
                label_mismatches.append(img["filename"])
                continue
            
            try:
                # Check if image is corrupt - use load() for full validation
                with Image.open(img_path) as pil_img:
                    pil_img.load()
                    width, height = pil_img.size
                
                # Calculate image hash for duplicate detection
                with open(img_path, 'rb') as f:
                    img_hash = hashlib.md5(f.read()).hexdigest()
                    if img_hash in image_hashes:
                        image_hashes[img_hash].append(img["filename"])
                    else:
                        image_hashes[img_hash] = [img["filename"]]
                
                # Validate annotation dimensions match image
                if annotation["width"] != width or annotation["height"] != height:
                    label_mismatches.append(img["filename"])
                
            except Exception as e:
                corrupt_images.append(img["filename"])
                logger.warning(f"Corrupt image {img['filename']}: {e}")
                continue
            
            # Process boxes with full validation
            boxes = annotation.get("boxes", [])
            
            # Check for empty annotations
            if not boxes:
                empty_annotations.append(img["filename"])
            
            img_width = annotation["width"]
            img_height = annotation["height"]
            
            for box in boxes:
                # Validate class
                class_name = box.get("class_name", "")
                class_id = box.get("class_id", -1)
                
                # Check if class exists in dataset
                if class_name and class_name not in dataset_classes:
                    invalid_class_ids.append(f"{img['filename']}: class '{class_name}' not in dataset")
                
                # Validate class_id is within valid range
                if class_id < 0 or class_id >= len(dataset_classes):
                    invalid_class_ids.append(f"{img['filename']}: invalid class_id {class_id}")
                
                # Get box coordinates
                box_x = box.get("x", 0)
                box_y = box.get("y", 0)
                box_width = box.get("width", 0)
                box_height = box.get("height", 0)
                
                # Validate box coordinates are within image bounds
                box_x_max = box_x + box_width
                box_y_max = box_y + box_height
                
                if box_x < 0 or box_y < 0 or box_x_max > img_width or box_y_max > img_height:
                    boxes_out_of_bounds.append(f"{img['filename']}: box ({box_x}, {box_y}, {box_width}, {box_height}) out of bounds")
                    invalid_boxes.append(box)
                    continue
                
                # Validate box dimensions
                if box_width <= 0 or box_height <= 0:
                    invalid_boxes.append(box)
                    continue
                
                # Box is valid - add to analysis
                all_annotations.append(box)
                
                if class_name:
                    class_counts[class_name] += 1
                
                # Calculate object size and aspect ratio
                img_area = img_width * img_height
                box_area = box_width * box_height
                
                if img_area > 0:
                    relative_size = box_area / img_area
                    object_sizes.append(relative_size)
                    
                    if box_width > 0 and box_height > 0:
                        aspect_ratio = box_width / box_height
                        aspect_ratios.append(aspect_ratio)
        
        # Class distribution analysis
        class_frequency = dict(class_counts)
        class_balance_score = DatasetAnalyzer._calculate_class_balance(class_frequency)
        
        # Object size distribution
        size_dist = DatasetAnalyzer._categorize_sizes(object_sizes)
        
        # Aspect ratio distribution
        aspect_dist = DatasetAnalyzer._categorize_aspect_ratios(aspect_ratios)
        
        # Duplicate detection
        duplicates = [files for files in image_hashes.values() if len(files) > 1]
        duplicate_filenames = [f for files in duplicates for f in files[1:]]  # Skip first occurrence
        
        # Structure validation
        structure_valid, structure_issues = DatasetAnalyzer._validate_structure(dataset_id, dataset)
        
        # Add YOLO label file validation issues to structure issues
        label_file_issues = DatasetAnalyzer._validate_yolo_label_files(dataset_id, annotated_images)
        structure_issues.extend(label_file_issues)
        if label_file_issues:
            structure_valid = False
        
        # Split analysis
        split_dist, split_ratios, data_leakage = DatasetAnalyzer._analyze_splits(annotated_images, image_hashes)
        
        # Quality scores
        label_accuracy = DatasetAnalyzer._calculate_label_accuracy(
            annotated_images, 
            label_mismatches, 
            corrupt_images,
            len(invalid_boxes),
            len(empty_annotations),
            len(boxes_out_of_bounds)
        )
        iou_consistency = DatasetAnalyzer._calculate_iou_consistency(all_annotations)
        
        # Recommendations
        recommended_config = DatasetAnalyzer._recommend_training_config(
            len(annotated_images),
            len(class_frequency),
            class_balance_score,
            size_dist
        )
        
        augmentation_recs = DatasetAnalyzer._recommend_augmentation(
            class_balance_score,
            size_dist,
            len(annotated_images)
        )
        
        # Overall quality score
        quality_score = DatasetAnalyzer._calculate_quality_score(
            class_balance_score,
            label_accuracy,
            iou_consistency,
            len(corrupt_images),
            len(duplicate_filenames),
            len(label_mismatches),
            len(annotated_images),
            data_leakage,
            len(invalid_boxes),
            len(empty_annotations),
            len(boxes_out_of_bounds),
            len(invalid_class_ids)
        )
        
        # Generate warnings and recommendations
        warnings, recommendations = DatasetAnalyzer._generate_warnings_recommendations(
            dataset,
            class_frequency,
            class_balance_score,
            size_dist,
            len(annotated_images),
            len(corrupt_images),
            len(duplicate_filenames),
            len(label_mismatches),
            split_ratios,
            data_leakage,
            quality_score,
            len(invalid_boxes),
            len(empty_annotations),
            len(boxes_out_of_bounds),
            len(invalid_class_ids)
        )
        
        return DatasetAnalysis(
            dataset_id=dataset_id,
            dataset_name=dataset.get("name", ""),
            total_images=len(images),
            annotated_images=len(annotated_images),
            total_annotations=len(all_annotations),
            classes=dataset.get("classes", []),
            class_frequency=class_frequency,
            class_balance_score=class_balance_score,
            object_size_distribution=size_dist,
            aspect_ratio_distribution=aspect_dist,
            avg_objects_per_image=len(all_annotations) / len(annotated_images) if annotated_images else 0,
            structure_valid=structure_valid,
            structure_issues=structure_issues,
            label_accuracy_score=label_accuracy,
            iou_consistency_score=iou_consistency,
            duplicate_images=duplicate_filenames,
            corrupt_images=corrupt_images,
            label_mismatches=label_mismatches,
            invalid_boxes=[f"Box {i+1}" for i in range(len(invalid_boxes))],
            empty_annotations=empty_annotations,
            invalid_class_ids=invalid_class_ids,
            boxes_out_of_bounds=boxes_out_of_bounds,
            split_distribution=split_dist,
            split_ratios=split_ratios,
            data_leakage_detected=data_leakage,
            recommended_image_size=recommended_config["image_size"],
            recommended_batch_size=recommended_config["batch_size"],
            recommended_epochs=recommended_config["epochs"],
            augmentation_recommendations=augmentation_recs,
            overall_quality_score=quality_score,
            warnings=warnings,
            recommendations=recommendations
        )
    
    @staticmethod
    def _calculate_class_balance(class_frequency: Dict[str, int]) -> float:
        """Calculate class balance score (0-1)"""
        if not class_frequency:
            return 0.0
        
        counts = list(class_frequency.values())
        if len(counts) == 1:
            return 1.0
        
        # Coefficient of variation (lower is better)
        if HAS_NUMPY:
            mean_count = np.mean(counts)
            if mean_count == 0:
                return 0.0
            std_count = np.std(counts)
        else:
            mean_count = mean(counts)
            if mean_count == 0:
                return 0.0
            std_count = std(counts)
        
        cv = std_count / mean_count
        
        # Convert to 0-1 score (lower CV = higher score)
        # CV of 0 = perfect balance (score 1.0)
        # CV of 1+ = very imbalanced (score approaches 0)
        score = max(0.0, 1.0 - min(cv, 1.0))
        return float(score)
    
    @staticmethod
    def _categorize_sizes(sizes: List[float]) -> Dict[str, int]:
        """Categorize object sizes"""
        dist = {"tiny": 0, "small": 0, "medium": 0, "large": 0}
        for size in sizes:
            if size < DatasetAnalyzer.TINY_THRESHOLD:
                dist["tiny"] += 1
            elif size < DatasetAnalyzer.SMALL_THRESHOLD:
                dist["small"] += 1
            elif size < DatasetAnalyzer.MEDIUM_THRESHOLD:
                dist["medium"] += 1
            else:
                dist["large"] += 1
        return dist
    
    @staticmethod
    def _categorize_aspect_ratios(ratios: List[float]) -> Dict[str, int]:
        """Categorize aspect ratios"""
        dist = {"portrait": 0, "square": 0, "landscape": 0}
        for ratio in ratios:
            if ratio < 0.8:
                dist["portrait"] += 1
            elif ratio > 1.2:
                dist["landscape"] += 1
            else:
                dist["square"] += 1
        return dist
    
    @staticmethod
    def _validate_structure(dataset_id: str, dataset: Dict) -> Tuple[bool, List[str]]:
        """Validate dataset structure"""
        issues = []
        dataset_path = Path(f"datasets/{dataset_id}")
        
        # Check directories
        if not dataset_path.exists():
            issues.append("Dataset directory does not exist")
            return False, issues
        
        images_dir = dataset_path / "images"
        labels_dir = dataset_path / "labels"
        
        if not images_dir.exists():
            issues.append("Images directory missing")
        if not labels_dir.exists():
            issues.append("Labels directory missing")
        
        # Check data.yaml if exists
        yaml_path = dataset_path / "data.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, 'r') as f:
                    yaml_data = yaml.safe_load(f)
                    if "names" not in yaml_data:
                        issues.append("data.yaml missing 'names' field")
                    if "nc" not in yaml_data:
                        issues.append("data.yaml missing 'nc' field")
                    if yaml_data.get("nc", 0) != len(dataset.get("classes", [])):
                        issues.append("data.yaml class count mismatch")
            except Exception as e:
                issues.append(f"Invalid data.yaml: {e}")
        
        return len(issues) == 0, issues
    
    @staticmethod
    def _analyze_splits(images: List[Dict], image_hashes: Dict[str, List[str]]) -> Tuple[Dict[str, int], Dict[str, float], bool]:
        """Analyze dataset splits"""
        split_counts = Counter(img.get("split") or "none" for img in images)
        split_dist = dict(split_counts)
        
        total = len(images)
        if total == 0:
            return split_dist, {}, False
        
        split_ratios = {
            split: count / total 
            for split, count in split_dist.items()
        }
        
        # Check for data leakage (same image in multiple splits)
        data_leakage = False
        for hash_val, files in image_hashes.items():
            if len(files) > 1:
                # Check if same image appears in different splits
                splits = set()
                for img in images:
                    if img["filename"] in files:
                        splits.add(img.get("split") or "none")
                if len(splits) > 1:
                    data_leakage = True
                    break
        
        return split_dist, split_ratios, data_leakage
    
    @staticmethod
    def _validate_yolo_label_files(dataset_id: str, images: List[Dict]) -> List[str]:
        """Validate that YOLO label files exist and match database annotations"""
        issues = []
        dataset_path = Path(f"datasets/{dataset_id}")
        labels_dir = dataset_path / "labels"
        
        if not labels_dir.exists():
            return ["Labels directory does not exist"]
        
        for img in images:
            if not img.get("annotated", False):
                continue
            
            # Check if label file exists
            label_filename = f"{Path(img['filename']).stem}.txt"
            label_path = labels_dir / label_filename
            
            if not label_path.exists():
                issues.append(f"Missing label file: {label_filename}")
                continue
            
            # Validate label file format
            try:
                with open(label_path, 'r') as f:
                    lines = f.readlines()
                    
                for line_num, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split()
                    if len(parts) != 5:
                        issues.append(f"{label_filename}: line {line_num} has invalid format (expected 5 values)")
                        continue
                    
                    try:
                        class_id = int(parts[0])
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        
                        # Validate normalized coordinates (0-1)
                        if not (0 <= x_center <= 1 and 0 <= y_center <= 1 and 
                                0 <= width <= 1 and 0 <= height <= 1):
                            issues.append(f"{label_filename}: line {line_num} has coordinates out of range [0,1]")
                        
                        # Validate box doesn't extend beyond boundaries
                        if (x_center - width/2 < 0 or x_center + width/2 > 1 or
                            y_center - height/2 < 0 or y_center + height/2 > 1):
                            issues.append(f"{label_filename}: line {line_num} box extends beyond image boundaries")
                        
                    except ValueError:
                        issues.append(f"{label_filename}: line {line_num} has invalid numeric values")
                        
            except Exception as e:
                issues.append(f"{label_filename}: Error reading file - {e}")
        
        return issues
    
    @staticmethod
    def _calculate_label_accuracy(
        images: List[Dict], 
        mismatches: List[str], 
        corrupt: List[str],
        invalid_box_count: int,
        empty_count: int,
        out_of_bounds_count: int
    ) -> float:
        """Calculate label accuracy score with comprehensive validation"""
        if not images:
            return 0.0
        
        total = len(images)
        # Weight different error types
        errors = (
            len(mismatches) * 1.0 +  # Dimension mismatch is critical
            len(corrupt) * 1.0 +      # Corrupt images are critical
            invalid_box_count * 0.5 +  # Invalid boxes are less critical
            empty_count * 0.3 +        # Empty annotations are less critical
            out_of_bounds_count * 0.8  # Out of bounds is serious
        )
        accuracy = max(0.0, 1.0 - (errors / total))
        return float(accuracy)
    
    @staticmethod
    def _calculate_iou_consistency(annotations: List[Dict]) -> float:
        """Calculate IoU consistency - check for overlapping boxes and validate coordinates"""
        if len(annotations) < 2:
            return 1.0
        
        if not annotations:
            return 0.0
        
        valid_boxes = 0
        overlapping_pairs = 0
        total_pairs = 0
        
        # Check each box is well-formed
        for box in annotations:
            width = box.get("width", 0)
            height = box.get("height", 0)
            x = box.get("x", 0)
            y = box.get("y", 0)
            
            if width > 0 and height > 0 and x >= 0 and y >= 0:
                valid_boxes += 1
        
        # Check for overlapping boxes (simplified IoU check)
        for i, box1 in enumerate(annotations):
            x1 = box1.get("x", 0)
            y1 = box1.get("y", 0)
            w1 = box1.get("width", 0)
            h1 = box1.get("height", 0)
            
            if w1 <= 0 or h1 <= 0:
                continue
            
            x1_max = x1 + w1
            y1_max = y1 + h1
            
            for j, box2 in enumerate(annotations[i+1:], start=i+1):
                x2 = box2.get("x", 0)
                y2 = box2.get("y", 0)
                w2 = box2.get("width", 0)
                h2 = box2.get("height", 0)
                
                if w2 <= 0 or h2 <= 0:
                    continue
                
                total_pairs += 1
                
                x2_max = x2 + w2
                y2_max = y2 + h2
                
                # Check if boxes overlap
                if not (x1_max <= x2 or x2_max <= x1 or y1_max <= y2 or y2_max <= y1):
                    overlapping_pairs += 1
        
        # Score based on valid boxes and reasonable overlap ratio
        valid_ratio = valid_boxes / len(annotations) if annotations else 0.0
        
        # Some overlap is expected (objects can overlap), but excessive overlap is suspicious
        # Penalize if more than 30% of pairs overlap significantly
        overlap_penalty = 0.0
        if total_pairs > 0:
            overlap_ratio = overlapping_pairs / total_pairs
            if overlap_ratio > 0.3:  # More than 30% overlap is suspicious
                overlap_penalty = (overlap_ratio - 0.3) * 0.5  # Penalty up to 0.35
        
        final_score = max(0.0, valid_ratio - overlap_penalty)
        return float(final_score)
    
    @staticmethod
    def _recommend_training_config(
        num_images: int,
        num_classes: int,
        balance_score: float,
        size_dist: Dict[str, int]
    ) -> Dict[str, int]:
        """Recommend training configuration"""
        # Image size recommendation
        total_objects = sum(size_dist.values())
        tiny_ratio = size_dist.get("tiny", 0) / total_objects if total_objects > 0 else 0
        
        if tiny_ratio > 0.3:
            img_size = 1280  # Higher resolution for tiny objects
        elif tiny_ratio > 0.1:
            img_size = 640
        else:
            img_size = 640
        
        # Batch size recommendation
        if num_images < 100:
            batch_size = 8
        elif num_images < 500:
            batch_size = 16
        elif num_images < 2000:
            batch_size = 32
        else:
            batch_size = 64
        
        # Epochs recommendation
        if num_images < 100:
            epochs = 200
        elif num_images < 500:
            epochs = 150
        elif num_images < 2000:
            epochs = 100
        else:
            epochs = 50
        
        return {
            "image_size": img_size,
            "batch_size": batch_size,
            "epochs": epochs
        }
    
    @staticmethod
    def _recommend_augmentation(
        balance_score: float,
        size_dist: Dict[str, int],
        num_images: int
    ) -> Dict[str, Any]:
        """Recommend augmentation settings"""
        total_objects = sum(size_dist.values())
        tiny_ratio = size_dist.get("tiny", 0) / total_objects if total_objects > 0 else 0
        
        recommendations = {
            "mosaic": True if num_images < 1000 else False,
            "mixup": 0.1 if balance_score < 0.7 else 0.0,
            "hsv_h": 0.015,
            "hsv_s": 0.7,
            "hsv_v": 0.4,
            "flip": 0.5,
            "scale": 0.5 if tiny_ratio < 0.2 else 0.3,
            "degrees": 10.0 if tiny_ratio > 0.1 else 0.0,
            "translate": 0.1,
            "blur": 0.0,
            "noise": 0.0
        }
        
        return recommendations
    
    @staticmethod
    def _calculate_quality_score(
        balance_score: float,
        label_accuracy: float,
        iou_consistency: float,
        corrupt_count: int,
        duplicate_count: int,
        mismatch_count: int,
        total_images: int,
        data_leakage: bool,
        invalid_box_count: int,
        empty_count: int,
        out_of_bounds_count: int,
        invalid_class_count: int
    ) -> float:
        """Calculate overall quality score (0-100) with comprehensive validation"""
        if total_images == 0:
            return 0.0
        
        # Base scores (weighted)
        base_score = (
            balance_score * 0.25 +
            label_accuracy * 0.35 +
            iou_consistency * 0.25 +
            (1.0 if invalid_class_count == 0 else 0.5) * 0.15  # Class validation
        ) * 100
        
        # Penalties (weighted by severity)
        critical_errors = corrupt_count + mismatch_count + out_of_bounds_count
        moderate_errors = duplicate_count + invalid_box_count
        minor_errors = empty_count + invalid_class_count
        
        error_penalty = (
            (critical_errors / total_images) * 40 +      # Critical errors heavily penalize
            (moderate_errors / total_images) * 20 +      # Moderate errors moderate penalty
            (minor_errors / total_images) * 10           # Minor errors light penalty
        )
        
        leakage_penalty = 25 if data_leakage else 0
        
        final_score = max(0.0, base_score - error_penalty - leakage_penalty)
        return float(final_score)
    
    @staticmethod
    def _generate_warnings_recommendations(
        dataset: Dict,
        class_frequency: Dict[str, int],
        balance_score: float,
        size_dist: Dict[str, int],
        num_images: int,
        corrupt_count: int,
        duplicate_count: int,
        mismatch_count: int,
        split_ratios: Dict[str, float],
        data_leakage: bool,
        quality_score: float,
        invalid_box_count: int,
        empty_count: int,
        out_of_bounds_count: int,
        invalid_class_count: int
    ) -> Tuple[List[str], List[str]]:
        """Generate warnings and recommendations"""
        warnings = []
        recommendations = []
        
        # Class balance warnings
        if balance_score < 0.5:
            warnings.append("Severe class imbalance detected")
            recommendations.append("Consider using class weights or oversampling rare classes")
        elif balance_score < 0.7:
            warnings.append("Moderate class imbalance detected")
            recommendations.append("Consider data augmentation for minority classes")
        
        # Dataset size warnings
        min_per_class = min(class_frequency.values()) if class_frequency else 0
        if min_per_class < 10:
            warnings.append(f"Some classes have very few examples (< 10)")
            recommendations.append("Collect more data for underrepresented classes")
        elif min_per_class < 50:
            warnings.append(f"Some classes have limited examples (< 50)")
            recommendations.append("Consider data augmentation or transfer learning")
        
        if num_images < 100:
            warnings.append("Small dataset size may lead to overfitting")
            recommendations.append("Use aggressive data augmentation and consider transfer learning")
        
        # Object size warnings
        total_objects = sum(size_dist.values())
        if total_objects > 0:
            tiny_ratio = size_dist.get("tiny", 0) / total_objects
            if tiny_ratio > 0.3:
                warnings.append("High proportion of tiny objects detected")
                recommendations.append("Use higher image resolution (1280px) and consider mosaic augmentation")
        
        # Quality warnings
        if corrupt_count > 0:
            warnings.append(f"{corrupt_count} corrupt images detected")
            recommendations.append("Remove or fix corrupt images before training")
        
        if duplicate_count > 0:
            warnings.append(f"{duplicate_count} duplicate images detected")
            recommendations.append("Remove duplicate images to prevent data leakage")
        
        if mismatch_count > 0:
            warnings.append(f"{mismatch_count} label mismatches detected")
            recommendations.append("Fix label mismatches (annotation dimensions don't match image)")
        
        if invalid_box_count > 0:
            warnings.append(f"{invalid_box_count} invalid bounding boxes detected")
            recommendations.append("Fix invalid bounding boxes (zero or negative dimensions)")
        
        if empty_count > 0:
            warnings.append(f"{empty_count} images with no annotations detected")
            recommendations.append("Remove unannotated images or add annotations before training")
        
        if out_of_bounds_count > 0:
            warnings.append(f"{out_of_bounds_count} bounding boxes extend beyond image boundaries")
            recommendations.append("Fix out-of-bounds boxes - they will cause training errors")
        
        if invalid_class_count > 0:
            warnings.append(f"{invalid_class_count} invalid class IDs detected")
            recommendations.append("Fix class IDs to match dataset class list")
        
        # Split warnings
        if "train" in split_ratios:
            train_ratio = split_ratios["train"]
            if train_ratio < 0.7:
                warnings.append("Training set is too small (< 70%)")
                recommendations.append("Increase training set size or use cross-validation")
        
        if data_leakage:
            warnings.append("Data leakage detected - same images in multiple splits")
            recommendations.append("Fix split assignments to prevent data leakage")
        
        # Overall quality
        if quality_score < 50:
            warnings.append("Low overall dataset quality")
            recommendations.append("Address quality issues before training for best results")
        elif quality_score < 70:
            warnings.append("Moderate dataset quality")
            recommendations.append("Consider improving dataset quality for better model performance")
        
        return warnings, recommendations
