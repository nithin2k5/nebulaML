import hashlib
import json
from typing import Dict, List, Any
import numpy as np
from pathlib import Path

from app.services.database import DatasetService, AnnotationService
from app.db.session import get_db_connection

def prepare_splits(dataset_id: str, split_ratio: Dict = None) -> None:
    """
    Assigns splits to all annotated images that currently have split=None.
    This must be run before preflight so Stage D sees real split values.
    """
    if split_ratio is None:
        split_ratio = {"train": 0.8, "val": 0.1, "test": 0.1}
        
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset: return
    
    images = dataset.get('images', [])
    annotated_images = [img for img in images if img.get('annotated')]
    
    needs_split = [img for img in annotated_images if not img.get('split')]
    if not needs_split:
        return
        
    # Deterministic random split assignment
    seed = int(hashlib.md5(dataset_id.encode()).hexdigest(), 16) % (2 ** 31)
    rng = np.random.default_rng(seed)
    # Convert to list and shuffle
    needs_split = list(needs_split)
    rng.shuffle(needs_split)
    
    n_train = int(len(needs_split) * split_ratio.get('train', 0.8))
    n_val = int(len(needs_split) * split_ratio.get('val', 0.1))
    n_test = len(needs_split) - n_train - n_val
    
    splits = ['train'] * n_train + ['val'] * n_val + ['test'] * n_test
    
    for img_data, split in zip(needs_split, splits):
        DatasetService.update_image_split(dataset_id, img_data['id'], split)


def compute_manifest(dataset_id: str) -> Dict[str, Any]:
    """
    Computes a content hash of the dataset's current state.
    Includes: image bytes + label bytes + split assignment.
    Must run under a single connection to ensure read isolation.
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed")
        
    try:
        # Use a single connection for reading to minimize interleaving
        cursor = conn.cursor(dictionary=True)
        cursor.execute("START TRANSACTION READ ONLY")
        
        # Read dataset images
        cursor.execute("""
            SELECT id, filename, path, split, annotated
            FROM dataset_images 
            WHERE dataset_id = %s AND annotated = TRUE
        """, (dataset_id,))
        images = cursor.fetchall()
        
        image_tuples = []
        for img in images:
            img_id = img["id"]
            img_path = Path(img["path"])
            split = img.get("split") or "none"
            
            # Fetch annotation for this image
            cursor.execute("""
                SELECT boxes
                FROM annotations
                WHERE dataset_id = %s AND image_id = %s
            """, (dataset_id, img_id))
            ann_row = cursor.fetchone()
            
            label_bytes = b""
            if ann_row and ann_row.get("boxes"):
                # We use the JSON dump of the boxes as the label content
                label_bytes = json.dumps(json.loads(ann_row["boxes"]), sort_keys=True).encode("utf-8")
                
            img_bytes = b""
            if img_path.exists():
                try:
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()
                except Exception:
                    pass
                    
            # Compute per-image hash
            h = hashlib.sha256()
            h.update(img_bytes)
            h.update(label_bytes)
            image_hash = h.hexdigest()
            
            image_tuples.append((img_id, image_hash, split))
            
        cursor.execute("COMMIT")
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
        
    # Sort tuples to ensure deterministic manifest hash
    image_tuples.sort(key=lambda x: x[0])
    
    manifest_h = hashlib.sha256()
    for t in image_tuples:
        manifest_h.update(f"{t[0]}:{t[1]}:{t[2]}".encode("utf-8"))
        
    return {
        "manifest_hash": manifest_h.hexdigest(),
        "image_count": len(image_tuples),
        "tuples": image_tuples
    }

class PreflightResultService:
    @staticmethod
    def get_latest(dataset_id: str) -> Dict[str, Any]:
        file_path = Path(f"datasets/{dataset_id}/preflight_result.json")
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            return None
            
    @staticmethod
    def save_result(dataset_id: str, result: Dict[str, Any]) -> None:
        file_path = Path(f"datasets/{dataset_id}/preflight_result.json")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(result, f)

