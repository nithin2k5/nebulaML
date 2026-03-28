"""
Database service for dataset and annotation operations
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.db.session import get_db_connection
from mysql.connector import Error


class DatasetService:
    """Service for dataset database operations"""
    
    @staticmethod
    def create_dataset(dataset_id: str, name: str, classes: List[str], 
                      description: str = "", user_id: Optional[int] = None) -> bool:
        """Create a new dataset in database"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO datasets (id, user_id, name, description, classes, total_images, annotated_images)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (dataset_id, user_id, name, description, json.dumps(classes), 0, 0))
            connection.commit()
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error creating dataset: {e}")
            if connection:
                connection.close()
            return False
    
    @staticmethod
    def get_dataset(dataset_id: str) -> Optional[Dict]:
        """Get dataset by ID"""
        connection = get_db_connection()
        if not connection:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, user_id, name, description, classes, total_images, annotated_images,
                       created_at, updated_at
                FROM datasets WHERE id = %s
            """, (dataset_id,))
            dataset = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if dataset:
                dataset['classes'] = json.loads(dataset['classes'])
                dataset['images'] = DatasetService.get_dataset_images(dataset_id)
            return dataset
        except Error as e:
            print(f"Error getting dataset: {e}")
            if connection:
                connection.close()
            return None
    
    @staticmethod
    def list_datasets(user_id: Optional[int] = None) -> List[Dict]:
        """List all datasets, optionally filtered by user_id"""
        connection = get_db_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            if user_id:
                cursor.execute("""
                    SELECT id, user_id, name, description, classes, total_images, annotated_images,
                           created_at, updated_at
                    FROM datasets WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT id, user_id, name, description, classes, total_images, annotated_images,
                           created_at, updated_at
                    FROM datasets
                    ORDER BY created_at DESC
                """)
            
            datasets = cursor.fetchall()
            cursor.close()
            connection.close()
            
            for dataset in datasets:
                dataset['classes'] = json.loads(dataset['classes'])
                dataset['images'] = DatasetService.get_dataset_images(dataset['id'])
            
            return datasets
        except Error as e:
            print(f"Error listing datasets: {e}")
            if connection:
                connection.close()
            return []
    
    @staticmethod
    def update_dataset(dataset_id: str, **kwargs) -> bool:
        """Update dataset fields"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            updates = []
            values = []
            
            if 'name' in kwargs:
                updates.append("name = %s")
                values.append(kwargs['name'])
            if 'description' in kwargs:
                updates.append("description = %s")
                values.append(kwargs['description'])
            if 'classes' in kwargs:
                updates.append("classes = %s")
                values.append(json.dumps(kwargs['classes']))
            
            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                values.append(dataset_id)
                query = f"UPDATE datasets SET {', '.join(updates)} WHERE id = %s"
                cursor.execute(query, values)
                connection.commit()
            
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error updating dataset: {e}")
            if connection:
                connection.close()
            return False
    
    @staticmethod
    def delete_dataset(dataset_id: str) -> bool:
        """Delete dataset and all related data"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM datasets WHERE id = %s", (dataset_id,))
            connection.commit()
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error deleting dataset: {e}")
            if connection:
                connection.close()
            return False
    
    @staticmethod
    def add_image(dataset_id: str, image_id: str, filename: str, 
                  original_name: str, path: str) -> bool:
        """Add image to dataset"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO dataset_images (id, dataset_id, filename, original_name, path, annotated, split)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (image_id, dataset_id, filename, original_name, path, False, None))
            connection.commit()
            
            # Update total_images count
            cursor.execute("""
                UPDATE datasets 
                SET total_images = (SELECT COUNT(*) FROM dataset_images WHERE dataset_id = %s),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (dataset_id, dataset_id))
            connection.commit()
            
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error adding image: {e}")
            if connection:
                connection.close()
            return False
    
    @staticmethod
    def get_dataset_images(dataset_id: str) -> List[Dict]:
        """Get all images for a dataset"""
        connection = get_db_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, filename, original_name, path, annotated, split, uploaded_at
                FROM dataset_images
                WHERE dataset_id = %s
                ORDER BY uploaded_at ASC
            """, (dataset_id,))
            images = cursor.fetchall()
            cursor.close()
            connection.close()
            return images
        except Error as e:
            print(f"Error getting images: {e}")
            if connection:
                connection.close()
            return []
    
    @staticmethod
    def update_image_split(dataset_id: str, image_id: str, split: Optional[str]) -> bool:
        """Update image split assignment"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE dataset_images
                SET split = %s
                WHERE id = %s AND dataset_id = %s
            """, (split, image_id, dataset_id))
            connection.commit()
            
            cursor.execute("""
                UPDATE datasets SET updated_at = CURRENT_TIMESTAMP WHERE id = %s
            """, (dataset_id,))
            connection.commit()
            
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error updating image split: {e}")
            if connection:
                connection.close()
            return False
    
    @staticmethod
    def mark_image_annotated(dataset_id: str, image_id: str, annotated: bool = True) -> bool:
        """Mark image as annotated"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE dataset_images
                SET annotated = %s
                WHERE id = %s AND dataset_id = %s
            """, (annotated, image_id, dataset_id))
            connection.commit()
            
            # Update annotated_images count
            cursor.execute("""
                UPDATE datasets 
                SET annotated_images = (SELECT COUNT(*) FROM dataset_images WHERE dataset_id = %s AND annotated = TRUE),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (dataset_id, dataset_id))
            connection.commit()
            
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error marking image annotated: {e}")
            if connection:
                connection.close()
            return False


class AnnotationService:
    """Service for annotation database operations"""
    
    @staticmethod
    def save_annotation(annotation_id: str, dataset_id: str, image_id: str,
                       image_name: str, width: int, height: int, boxes: List[Dict],
                       split: Optional[str] = None, status: str = "annotated") -> bool:
        """Save annotation to database"""
        connection = get_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            # Check if annotation exists
            cursor.execute("SELECT id FROM annotations WHERE id = %s", (annotation_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Update existing
                cursor.execute("""
                    UPDATE annotations
                    SET boxes = %s, width = %s, height = %s, split = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (json.dumps(boxes), width, height, split, status, annotation_id))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO annotations (id, dataset_id, image_id, image_name, width, height, boxes, split, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (annotation_id, dataset_id, image_id, image_name, width, height, json.dumps(boxes), split, status))
            
            connection.commit()
            
            # Only mark as annotated when the image actually has labels
            is_annotated = len(boxes) > 0 and status not in ("unlabeled",)
            DatasetService.mark_image_annotated(dataset_id, image_id, is_annotated)
            
            # Update image split if provided
            if split:
                DatasetService.update_image_split(dataset_id, image_id, split)
            
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error saving annotation: {e}")
            if connection:
                connection.close()
            return False
    
    @staticmethod
    def get_annotation(dataset_id: str, image_id: str) -> Optional[Dict]:
        """Get annotation for an image"""
        connection = get_db_connection()
        if not connection:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            annotation_id = f"{dataset_id}_{image_id}"
            cursor.execute("""
                SELECT id, dataset_id, image_id, image_name, width, height, boxes, split, status, created_at, updated_at
                FROM annotations
                WHERE id = %s
            """, (annotation_id,))
            annotation = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if annotation:
                annotation['boxes'] = json.loads(annotation['boxes'])
            return annotation
        except Error as e:
            print(f"Error getting annotation: {e}")
            if connection:
                connection.close()
            return None
    
    @staticmethod
    def get_dataset_stats(dataset_id: str) -> Dict:
        """Get dataset statistics"""
        connection = get_db_connection()
        if not connection:
            return {}
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Get dataset info
            cursor.execute("""
                SELECT name, classes FROM datasets WHERE id = %s
            """, (dataset_id,))
            dataset = cursor.fetchone()
            
            if not dataset:
                return {}
            
            classes = json.loads(dataset['classes'])
            
            # Get image counts
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_images,
                    SUM(CASE WHEN annotated = TRUE THEN 1 ELSE 0 END) as annotated_images
                FROM dataset_images
                WHERE dataset_id = %s
            """, (dataset_id,))
            counts = cursor.fetchone()
            
            # Get split counts
            cursor.execute("""
                SELECT split, COUNT(*) as count
                FROM dataset_images
                WHERE dataset_id = %s AND split IS NOT NULL
                GROUP BY split
            """, (dataset_id,))
            split_counts = {row['split']: row['count'] for row in cursor.fetchall()}
            
            # Get class counts from annotations
            cursor.execute("""
                SELECT boxes FROM annotations WHERE dataset_id = %s
            """, (dataset_id,))
            all_boxes = []
            for row in cursor.fetchall():
                boxes = json.loads(row['boxes'])
                all_boxes.extend(boxes)
            
            class_counts = {cls: 0 for cls in classes}
            for box in all_boxes:
                class_name = box.get('class_name', '')
                if class_name in class_counts:
                    class_counts[class_name] += 1
            
            cursor.close()
            connection.close()
            
            return {
                "dataset_id": dataset_id,
                "name": dataset['name'],
                "total_images": counts['total_images'] or 0,
                "annotated_images": counts['annotated_images'] or 0,
                "unannotated_images": (counts['total_images'] or 0) - (counts['annotated_images'] or 0),
                "total_classes": len(classes),
                "class_counts": class_counts,
                "split_counts": split_counts,
                "completion_percentage": (
                    (counts['annotated_images'] or 0) / (counts['total_images'] or 1) * 100
                    if counts['total_images'] else 0
                )
            }
        except Error as e:
            print(f"Error getting dataset stats: {e}")
            if connection:
                connection.close()
            return {}

class DatasetVersionService:
    """Service for dataset version database operations"""
    
    @staticmethod
    def create_version(version_id: str, dataset_id: str, version_number: int,
                       name: str = "", preprocessing: Dict = None, 
                       augmentations: Dict = None, yaml_path: str = "") -> bool:
        """Create a new dataset version snapshot"""
        if preprocessing is None: preprocessing = {}
        if augmentations is None: augmentations = {}
        
        connection = get_db_connection()
        if not connection: return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO dataset_versions (id, dataset_id, version_number, name, preprocessing, augmentations, total_images, yaml_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (version_id, dataset_id, version_number, name, json.dumps(preprocessing), json.dumps(augmentations), 0, yaml_path))
            connection.commit()
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error creating dataset version: {e}")
            if connection: connection.close()
            return False

    @staticmethod
    def add_version_image(image_id: str, version_id: str, original_image_id: str, 
                          filename: str, path: str, width: int, height: int, split: str = "train", boxes: List[Dict] = None) -> bool:
        """Add an immutable processed image to a specific version"""
        if boxes is None: boxes = []
        connection = get_db_connection()
        if not connection: return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO dataset_version_images (id, version_id, original_image_id, filename, path, split, width, height, boxes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (image_id, version_id, original_image_id, filename, path, split, width, height, json.dumps(boxes)))
            connection.commit()
            
            # Update total_images count
            cursor.execute("""
                UPDATE dataset_versions 
                SET total_images = (SELECT COUNT(*) FROM dataset_version_images WHERE version_id = %s)
                WHERE id = %s
            """, (version_id, version_id))
            connection.commit()
            
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error adding version image: {e}")
            if connection: connection.close()
            return False
            
    @staticmethod
    def get_version(version_id: str) -> Optional[Dict]:
        """Get dataset version by ID including images"""
        connection = get_db_connection()
        if not connection: return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, dataset_id, version_number, name, preprocessing, augmentations, total_images, yaml_path, created_at
                FROM dataset_versions WHERE id = %s
            """, (version_id,))
            version = cursor.fetchone()
            
            if version:
                version['preprocessing'] = json.loads(version['preprocessing']) if version['preprocessing'] else {}
                version['augmentations'] = json.loads(version['augmentations']) if version['augmentations'] else {}
                
                cursor.execute("""
                    SELECT id, original_image_id, filename, path, split, width, height, boxes, created_at
                    FROM dataset_version_images WHERE version_id = %s
                """, (version_id,))
                images = cursor.fetchall()
                for img in images:
                    img['boxes'] = json.loads(img['boxes']) if img['boxes'] else []
                version['images'] = images
                
            cursor.close()
            connection.close()
            return version
        except Error as e:
            print(f"Error getting dataset version: {e}")
            if connection: connection.close()
            return None
            
    @staticmethod
    def list_dataset_versions(dataset_id: str) -> List[Dict]:
        """List all versions for a specific dataset"""
        connection = get_db_connection()
        if not connection: return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, dataset_id, version_number, name, preprocessing, augmentations, total_images, yaml_path, created_at
                FROM dataset_versions WHERE dataset_id = %s ORDER BY version_number ASC
            """, (dataset_id,))
            versions = cursor.fetchall()
            cursor.close()
            connection.close()
            
            for v in versions:
                v['preprocessing'] = json.loads(v['preprocessing']) if v['preprocessing'] else {}
                v['augmentations'] = json.loads(v['augmentations']) if v['augmentations'] else {}
            return versions
        except Error as e:
            print(f"Error listing dataset versions: {e}")
            if connection: connection.close()
            return []


class TrainingJobService:
    """Persist training job state to the training_jobs table so restarts don't lose history."""

    @staticmethod
    def upsert_job(job_id: str, data: dict) -> bool:
        connection = get_db_connection()
        if not connection:
            return False
        try:
            cursor = connection.cursor()
            config = data.get("config", {})
            cursor.execute("""
                INSERT INTO training_jobs
                    (id, dataset_id, model_name, status, progress, epochs, batch_size, config, results, error_message, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    status       = VALUES(status),
                    progress     = VALUES(progress),
                    config       = VALUES(config),
                    results      = VALUES(results),
                    error_message = VALUES(error_message)
            """, (
                job_id,
                data.get("dataset_id"),
                config.get("model_name", ""),
                data.get("status", "pending"),
                int(data.get("progress", 0)),
                config.get("epochs", 0),
                config.get("batch_size", 16),
                json.dumps(config),
                json.dumps(data.get("results")) if data.get("results") else None,
                data.get("error"),
                data.get("created_at", datetime.now().isoformat()),
            ))
            connection.commit()
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error upserting training job: {e}")
            if connection:
                connection.close()
            return False

    @staticmethod
    def load_all_jobs() -> dict:
        """Load all persisted jobs as the in-memory dict format used by training.py."""
        connection = get_db_connection()
        if not connection:
            return {}
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, dataset_id, model_name, status, progress, epochs, batch_size,
                       config, results, error_message, created_at
                FROM training_jobs
                ORDER BY created_at ASC
            """)
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            jobs = {}
            for row in rows:
                config_data = json.loads(row["config"]) if row["config"] else {}
                jobs[row["id"]] = {
                    "status": row["status"],
                    "progress": row["progress"],
                    "dataset_id": row["dataset_id"],
                    "config": config_data,
                    "metrics": json.loads(row["results"]) if row["results"] else {},
                    "error": row["error_message"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
            return jobs
        except Error as e:
            print(f"Error loading training jobs: {e}")
            if connection:
                connection.close()
            return {}


class QualitySnapshotService:
    """Service for persisting and retrieving dataset quality analysis snapshots"""

    # Fields stored in list columns that we truncate before persisting to keep row size manageable
    _TRUNCATE_FIELDS = (
        "blurry_images", "dark_images", "overexposed_images", "low_contrast_images",
        "corrupt_images", "duplicate_images", "near_duplicate_images",
        "label_mismatches", "invalid_boxes", "empty_annotations",
        "invalid_class_ids", "boxes_out_of_bounds", "structure_issues",
        "warnings", "recommendations",
    )
    _MAX_LIST_LEN = 50

    @classmethod
    def _slim_snapshot(cls, analysis_dict: Dict) -> str:
        """Trim long list fields before JSON serialisation."""
        slim = dict(analysis_dict)
        for key in cls._TRUNCATE_FIELDS:
            if isinstance(slim.get(key), list) and len(slim[key]) > cls._MAX_LIST_LEN:
                slim[key] = slim[key][: cls._MAX_LIST_LEN]
        return json.dumps(slim, default=str)

    @staticmethod
    def save_snapshot(dataset_id: str, analysis_dict: Dict) -> bool:
        """Persist a quality analysis run to the database."""
        connection = get_db_connection()
        if not connection:
            return False
        try:
            cursor = connection.cursor()
            near_dup_count = len(analysis_dict.get("near_duplicate_images") or [])
            blurry_count = (analysis_dict.get("image_quality_flags") or {}).get("blurry", 0)
            slim_json = QualitySnapshotService._slim_snapshot(analysis_dict)
            cursor.execute(
                """
                INSERT INTO dataset_quality_snapshots
                    (dataset_id, overall_quality_score, class_balance_score,
                     label_accuracy_score, iou_consistency_score,
                     total_images, annotated_images,
                     duplicate_count, near_duplicate_count, corrupt_count, blurry_count,
                     full_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    dataset_id,
                    analysis_dict.get("overall_quality_score", 0),
                    analysis_dict.get("class_balance_score", 0),
                    analysis_dict.get("label_accuracy_score", 0),
                    analysis_dict.get("iou_consistency_score", 0),
                    analysis_dict.get("total_images", 0),
                    analysis_dict.get("annotated_images", 0),
                    len(analysis_dict.get("duplicate_images") or []),
                    near_dup_count,
                    len(analysis_dict.get("corrupt_images") or []),
                    blurry_count,
                    slim_json,
                ),
            )
            connection.commit()
            cursor.close()
            connection.close()
            return True
        except Error as e:
            print(f"Error saving quality snapshot: {e}")
            if connection:
                connection.close()
            return False

    @staticmethod
    def get_history(dataset_id: str, limit: int = 30) -> List[Dict]:
        """Return last N snapshots for a dataset ordered oldest-first (for trend charts)."""
        connection = get_db_connection()
        if not connection:
            return []
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, overall_quality_score, class_balance_score,
                       label_accuracy_score, iou_consistency_score,
                       total_images, annotated_images,
                       duplicate_count, near_duplicate_count, corrupt_count, blurry_count,
                       created_at
                FROM dataset_quality_snapshots
                WHERE dataset_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (dataset_id, limit),
            )
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            result = []
            for row in rows:
                row["created_at"] = row["created_at"].isoformat() if row["created_at"] else None
                result.append(dict(row))
            return result
        except Error as e:
            print(f"Error fetching quality history: {e}")
            if connection:
                connection.close()
            return []
