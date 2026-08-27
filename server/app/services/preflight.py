import logging
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict
from pathlib import Path
from PIL import Image
import hashlib

# Try importing imagehash for perceptual hashing
try:
    import imagehash
    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False

# Try importing numpy
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from app.services.database import DatasetService, AnnotationService

logger = logging.getLogger(__name__)

class PreflightPipeline:
    """
    Redesigned Preflight Pipeline (A -> B -> C -> D).
    Returns structured reports for each stage:
    {stage: str, check: str, severity: str, affected_count: int, sample_ids: list}
    """
    
    @staticmethod
    def run_all(dataset_id: str) -> Dict[str, Any]:
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")
            
        images = DatasetService.get_dataset_images(dataset_id)
        annotated_images = [img for img in images if img.get("annotated", False)]
        dataset_classes = dataset.get("classes", [])
        
        reports = []
        
        # We process images once and feed the data to stages
        processed_data = PreflightPipeline._extract_data(dataset_id, annotated_images)
        
        # Stage A: Structural Integrity
        stage_a_reports = PreflightPipeline._stage_a_structural(processed_data)
        reports.extend(stage_a_reports)
        
        # Stage B: Label Sanity
        stage_b_reports = PreflightPipeline._stage_b_sanity(processed_data, dataset_classes)
        reports.extend(stage_b_reports)
        
        # Stage C: Distributional
        stage_c_reports = PreflightPipeline._stage_c_distributional(processed_data, dataset_classes)
        reports.extend(stage_c_reports)
        
        # Stage D: Split Integrity
        stage_d_reports = PreflightPipeline._stage_d_split_integrity(processed_data, dataset_classes)
        reports.extend(stage_d_reports)
        
        # Final aggregation
        blockers = [r for r in reports if r['severity'] == 'blocking']
        warnings = [r for r in reports if r['severity'] == 'warning']
        
        return {
            "success": True,
            "dataset_id": dataset_id,
            "annotated_images": len(annotated_images),
            "reports": reports,
            "blockers": blockers,
            "warnings": warnings,
            "can_train": len(blockers) == 0
        }

    @staticmethod
    def _extract_data(dataset_id: str, annotated_images: List[Dict]) -> Dict[str, Any]:
        data = {
            "images": annotated_images,
            "corrupt_images": [],
            "annotations": {}, # img_id -> list of boxes
            "image_dims": {}, # img_id -> (w, h)
            "image_hashes": {}, # hash -> list of img_ids
            "phash_list": [], # (img_id, phash, dhash)
        }
        
        for img in annotated_images:
            img_id = img["id"]
            img_path = Path(img["path"])
            if not img_path.exists():
                data["corrupt_images"].append(img_id)
                continue
                
            try:
                with Image.open(img_path) as pil_img:
                    pil_img.load()
                    width, height = pil_img.size
                    data["image_dims"][img_id] = (width, height)
                    
                    if HAS_IMAGEHASH:
                        try:
                            ph = imagehash.phash(pil_img)
                            dh = imagehash.dhash(pil_img)
                            data["phash_list"].append((img_id, ph, dh))
                        except Exception:
                            pass
                            
                with open(img_path, 'rb') as f:
                    img_hash = hashlib.md5(f.read()).hexdigest()
                    if img_hash not in data["image_hashes"]:
                        data["image_hashes"][img_hash] = []
                    data["image_hashes"][img_hash].append(img_id)
                    
            except Exception as e:
                data["corrupt_images"].append(img_id)
                
            annotation = AnnotationService.get_annotation(dataset_id, img_id)
            if annotation:
                data["annotations"][img_id] = annotation.get("boxes", [])
            else:
                data["annotations"][img_id] = []
                
        return data

    @staticmethod
    def _stage_a_structural(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        reports = []
        # 1. Corrupt/unreadable images
        if data["corrupt_images"]:
            reports.append({
                "stage": "A_Structural",
                "check": "corrupt_images",
                "severity": "blocking",
                "affected_count": len(data["corrupt_images"]),
                "sample_ids": data["corrupt_images"][:10]
            })
            
        # 2. Annotation-image bounds mismatch, degenerate boxes
        bounds_mismatch = []
        degenerate_boxes = []
        orphaned_annotations = []
        
        epsilon = 1e-4
        for img_id, boxes in data["annotations"].items():
            if img_id not in data["image_dims"]:
                if len(boxes) > 0:
                    orphaned_annotations.append(img_id)
                continue
                
            img_w, img_h = data["image_dims"][img_id]
            for box in boxes:
                bw, bh = box.get("width", 0), box.get("height", 0)
                bx, by = box.get("x", 0), box.get("y", 0)
                
                # Degenerate
                if bw <= epsilon or bh <= epsilon:
                    degenerate_boxes.append(img_id)
                    continue
                    
                # Bounds mismatch
                if bx < 0 or by < 0 or (bx + bw) > img_w or (by + bh) > img_h:
                    bounds_mismatch.append(img_id)
                    
        # Remove duplicates
        bounds_mismatch = list(set(bounds_mismatch))
        degenerate_boxes = list(set(degenerate_boxes))
        
        if bounds_mismatch:
            reports.append({
                "stage": "A_Structural",
                "check": "bounds_mismatch",
                "severity": "blocking",
                "affected_count": len(bounds_mismatch),
                "sample_ids": bounds_mismatch[:10]
            })
            
        if degenerate_boxes:
            reports.append({
                "stage": "A_Structural",
                "check": "degenerate_boxes",
                "severity": "blocking",
                "affected_count": len(degenerate_boxes),
                "sample_ids": degenerate_boxes[:10]
            })
            
        if orphaned_annotations:
            reports.append({
                "stage": "A_Structural",
                "check": "orphaned_annotations",
                "severity": "blocking",
                "affected_count": len(orphaned_annotations),
                "sample_ids": orphaned_annotations[:10]
            })
            
        return reports

    @staticmethod
    def _stage_b_sanity(data: Dict[str, Any], classes: List[str]) -> List[Dict[str, Any]]:
        reports = []
        
        # 1. Near-zero area or full-image boxes
        suspicious_area = []
        class_ratios = defaultdict(list)
        
        for img_id, boxes in data["annotations"].items():
            if img_id not in data["image_dims"]: continue
            img_w, img_h = data["image_dims"][img_id]
            img_area = img_w * img_h
            if img_area == 0: continue
            
            for box in boxes:
                bw, bh = box.get("width", 0), box.get("height", 0)
                b_area = bw * bh
                rel_area = b_area / img_area
                
                if rel_area < 0.0001 or rel_area > 0.99:
                    suspicious_area.append(img_id)
                    
                cls_name = box.get("class_name")
                if cls_name and bw > 0 and bh > 0:
                    class_ratios[cls_name].append(bw / bh)
                    
        suspicious_area = list(set(suspicious_area))
        if suspicious_area:
            pct = (len(suspicious_area) / max(1, len(data["images"]))) * 100
            severity = "blocking" if pct > 10 else "warning"
            reports.append({
                "stage": "B_Sanity",
                "check": "suspicious_box_area",
                "severity": severity,
                "affected_count": len(suspicious_area),
                "sample_ids": suspicious_area[:10]
            })
            
        # 2. Per-class aspect ratio outliers (z-score)
        if HAS_NUMPY:
            for cls_name, ratios in class_ratios.items():
                if len(ratios) > 10:
                    r_arr = np.array(ratios)
                    mean_r = np.mean(r_arr)
                    std_r = np.std(r_arr)
                    if std_r > 0:
                        z_scores = np.abs((r_arr - mean_r) / std_r)
                        outliers = np.sum(z_scores > 3.0)
                        if outliers > 0:
                            reports.append({
                                "stage": "B_Sanity",
                                "check": "aspect_ratio_outliers",
                                "severity": "warning",
                                "affected_count": int(outliers),
                                "sample_ids": [cls_name]
                            })
                            
        # 3. Class name clustering to catch typos
        def edit_distance(s1, s2):
            if len(s1) < len(s2):
                return edit_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)
            prev = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                curr = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = prev[j + 1] + 1
                    deletions = curr[j] + 1
                    substitutions = prev[j] + (c1 != c2)
                    curr.append(min(insertions, deletions, substitutions))
                prev = curr
            return prev[-1]
            
        typo_suspects = []
        for i in range(len(classes)):
            for j in range(i + 1, len(classes)):
                c1, c2 = classes[i], classes[j]
                if len(c1) > 3 and len(c2) > 3 and edit_distance(c1, c2) <= 1:
                    typo_suspects.append(f"{c1} vs {c2}")
                    
        if typo_suspects:
            reports.append({
                "stage": "B_Sanity",
                "check": "class_name_typo_suspects",
                "severity": "warning",
                "affected_count": len(typo_suspects),
                "sample_ids": typo_suspects
            })

        return reports

    @staticmethod
    def _stage_c_distributional(data: Dict[str, Any], classes: List[str]) -> List[Dict[str, Any]]:
        reports = []
        
        # 1. Class imbalance
        class_counts = defaultdict(int)
        for boxes in data["annotations"].values():
            for box in boxes:
                c = box.get("class_name")
                if c: class_counts[c] += 1
                
        if len(class_counts) > 1:
            counts = list(class_counts.values())
            max_c = max(counts)
            min_c = min(counts)
            if min_c > 0 and max_c / min_c >= 10:
                most = max(class_counts, key=class_counts.get)
                least = min(class_counts, key=class_counts.get)
                reports.append({
                    "stage": "C_Distributional",
                    "check": "severe_class_imbalance",
                    "severity": "warning",
                    "affected_count": len(class_counts),
                    "sample_ids": [f"{most}:{max_c}", f"{least}:{min_c}"]
                })
                
        # 2. Perceptual-hash near-duplicate detection across splits
        near_dups = []
        if HAS_IMAGEHASH and data["phash_list"]:
            phash_list = data["phash_list"]
            img_id_to_split = {img["id"]: img.get("split", "none") for img in data["images"]}
            
            for i in range(len(phash_list)):
                id_a, ph_a, _ = phash_list[i]
                split_a = img_id_to_split.get(id_a)
                for j in range(i + 1, len(phash_list)):
                    id_b, ph_b, _ = phash_list[j]
                    split_b = img_id_to_split.get(id_b)
                    
                    if split_a != split_b and split_a != "none" and split_b != "none":
                        if ph_a - ph_b <= 10:  # Threshold
                            near_dups.append(id_a)
                            
        near_dups = list(set(near_dups))
        if near_dups:
            reports.append({
                "stage": "C_Distributional",
                "check": "cross_split_near_duplicates",
                "severity": "warning",
                "affected_count": len(near_dups),
                "sample_ids": near_dups[:10]
            })
            
        # 3. Spatial bias
        if HAS_NUMPY:
            class_centers = defaultdict(list)
            for img_id, boxes in data["annotations"].items():
                if img_id not in data["image_dims"]: continue
                img_w, img_h = data["image_dims"][img_id]
                for box in boxes:
                    cls_name = box.get("class_name")
                    bx, by, bw, bh = box.get("x", 0), box.get("y", 0), box.get("width", 0), box.get("height", 0)
                    if cls_name and img_w > 0 and img_h > 0:
                        cx = (bx + bw / 2) / img_w
                        cy = (by + bh / 2) / img_h
                        class_centers[cls_name].append((cx, cy))
                        
            spatial_bias_classes = []
            for cls_name, centers in class_centers.items():
                if len(centers) > 20:
                    arr = np.array(centers)
                    std_x, std_y = np.std(arr[:, 0]), np.std(arr[:, 1])
                    if std_x < 0.1 and std_y < 0.1:
                        spatial_bias_classes.append(cls_name)
                        
            if spatial_bias_classes:
                reports.append({
                    "stage": "C_Distributional",
                    "check": "spatial_bias",
                    "severity": "warning",
                    "affected_count": len(spatial_bias_classes),
                    "sample_ids": spatial_bias_classes
                })
                
        return reports

    @staticmethod
    def _stage_d_split_integrity(data: Dict[str, Any], classes: List[str]) -> List[Dict[str, Any]]:
        reports = []
        
        split_counts = defaultdict(int)
        class_val_presence = defaultdict(int)
        
        for img in data["images"]:
            split = img.get("split", "none")
            split_counts[split] += 1
            if split == "val":
                boxes = data["annotations"].get(img["id"], [])
                for b in boxes:
                    c = b.get("class_name")
                    if c: class_val_presence[c] += 1
                    
        if split_counts.get("train", 0) > 0 and split_counts.get("val", 0) == 0:
            reports.append({
                "stage": "D_Split",
                "check": "empty_validation_split",
                "severity": "warning",
                "affected_count": 1,
                "sample_ids": []
            })
            
        missing_val_classes = []
        for c in classes:
            if class_val_presence[c] == 0:
                missing_val_classes.append(c)
                
        if missing_val_classes and split_counts.get("val", 0) > 0:
            reports.append({
                "stage": "D_Split",
                "check": "classes_missing_in_val",
                "severity": "warning",
                "affected_count": len(missing_val_classes),
                "sample_ids": missing_val_classes
            })
            
        return reports
