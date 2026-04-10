from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Body, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import json
import shutil
from pathlib import Path
import tempfile
import uuid
from datetime import datetime
import aiofiles
import zipfile
import sys
import logging
from dataclasses import asdict
from PIL import Image, ImageOps, ImageFilter
import random
import copy


# Add parent directory to path for imports
# sys.path.append(str(Path(__file__).parent.parent.parent))
from app.services.database import DatasetService, AnnotationService
from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db_connection

# Role hierarchy: owner > admin > annotator > viewer
_ROLE_RANK = {"owner": 4, "admin": 3, "annotator": 2, "viewer": 1}


def _effective_role(dataset_id: str, user_id: int, owner_id: int) -> str | None:
    """Return the caller's effective role on a dataset, or None if no access."""
    if user_id == owner_id:
        return "owner"
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT role FROM project_members WHERE dataset_id = %s AND user_id = %s",
            (dataset_id, user_id),
        )
        row = cursor.fetchone()
        return row["role"] if row else None
    finally:
        conn.close()


def _require_role(dataset_id: str, user_id: int, owner_id: int, minimum: str) -> str:
    """Raise 403 unless the caller holds at least *minimum* role. Returns effective role."""
    role = _effective_role(dataset_id, user_id, owner_id)
    if role is None or _ROLE_RANK.get(role, 0) < _ROLE_RANK.get(minimum, 99):
        raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
    return role

router = APIRouter()
logger = logging.getLogger(__name__)

# Keep in-memory storage as fallback/backup
annotations_db: Dict[str, Dict] = {}
datasets_db: Dict[str, Dict] = {}
export_jobs: Dict[str, Dict] = {}
auto_label_jobs: Dict[str, Dict] = {}

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
    class_id: int
    class_name: str
    confidence: Optional[float] = 1.0

class ImageAnnotation(BaseModel):
    image_id: str
    image_name: str
    width: int
    height: int
    boxes: List[BoundingBox]
    status: Optional[str] = "annotated"  # unlabeled, predicted, annotated, reviewed

class Dataset(BaseModel):
    name: str
    description: Optional[str] = ""
    classes: List[str]

class ExportRequest(BaseModel):
    split_ratio: float = 0.8
    config: Optional[Dict[str, bool]] = None


@router.post("/datasets/create")
async def create_dataset(
    dataset: Dataset,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new dataset
    """
    dataset_id = str(uuid.uuid4())
    
    # Save to database
    success = DatasetService.create_dataset(
        dataset_id=dataset_id,
        name=dataset.name,
        classes=dataset.classes,
        description=dataset.description or "",
        user_id=current_user["id"]
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create dataset in database")
    
    # Also keep in memory for compatibility
    datasets_db[dataset_id] = {
        "id": dataset_id,
        "name": dataset.name,
        "description": dataset.description,
        "classes": dataset.classes,
        "images": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Create dataset directory
    dataset_dir = Path(f"datasets/{dataset_id}")
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "images").mkdir(exist_ok=True)
    (dataset_dir / "labels").mkdir(exist_ok=True)
    
    # Get from database to return complete data
    db_dataset = DatasetService.get_dataset(dataset_id)
    dataset_data = db_dataset or datasets_db[dataset_id]
    
    # Convert datetime objects to strings for JSON serialization
    return JSONResponse(content=jsonable_encoder({
        "success": True,
        "dataset_id": dataset_id,
        "dataset": dataset_data
    }))

@router.get("/datasets/list")
async def list_datasets(current_user: dict = Depends(get_current_user)):
    """
    List all datasets owned by or shared with the current user.
    """
    owned = DatasetService.list_datasets(user_id=current_user["id"])

    # Fetch datasets where the user is a project member but not the owner
    member_datasets = []
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT dataset_id FROM project_members WHERE user_id = %s",
                (current_user["id"],),
            )
            member_ids = [r["dataset_id"] for r in cursor.fetchall()]
            owned_ids = {d["id"] for d in owned}
            for did in member_ids:
                if did not in owned_ids:
                    ds = DatasetService.get_dataset(did)
                    if ds:
                        member_datasets.append(ds)
        finally:
            conn.close()

    all_datasets = owned + member_datasets
    for ds in all_datasets:
        datasets_db[ds["id"]] = ds

    return {"datasets": all_datasets}

@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get dataset details
    """
    # Get from database
    db_dataset = DatasetService.get_dataset(dataset_id)
    
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "viewer")

    # Sync with memory
    datasets_db[dataset_id] = db_dataset

    return db_dataset

@router.post("/datasets/{dataset_id}/upload")
async def upload_images_to_dataset(
    dataset_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload images to a dataset
    """
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "annotator")

    # Validate files list
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Create dataset directory if it doesn't exist
    dataset_dir = Path(f"datasets/{dataset_id}/images")
    dataset_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_files = []
    errors = []
    
    # Validate and process each file
    for file in files:
        try:
            # Check if file has a filename
            if not file.filename:
                errors.append("Unknown file: Missing filename")
                continue
            
            # Validate file type
            if not file.content_type or not file.content_type.startswith('image/'):
                errors.append(f"{file.filename}: Not a valid image file (content-type: {file.content_type})")
                continue
            
            image_id = str(uuid.uuid4())
            file_ext = Path(file.filename).suffix.lower()
            
            # If no extension, try to infer from content type
            if not file_ext:
                content_type_map = {
                    'image/jpeg': '.jpg',
                    'image/jpg': '.jpg',
                    'image/png': '.png',
                    'image/gif': '.gif',
                    'image/bmp': '.bmp',
                    'image/webp': '.webp'
                }
                file_ext = content_type_map.get(file.content_type, '.jpg')
            
            # Ensure valid extension
            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                errors.append(f"{file.filename}: Unsupported image format ({file_ext})")
                continue
            
            new_filename = f"{image_id}{file_ext}"
            file_path = dataset_dir / new_filename
            
            # Read and write file (with size check)
            file_content = await file.read()
            
            # Validate file size (max 50MB per file)
            if len(file_content) > 50 * 1024 * 1024:  # 50MB
                errors.append(f"{file.filename}: File too large (max 50MB, got {len(file_content) / 1024 / 1024:.2f}MB)")
                continue
            
            # Validate minimum file size (at least 100 bytes)
            if len(file_content) < 100:
                errors.append(f"{file.filename}: File too small or corrupted")
                continue
            
            # Write file
            async with aiofiles.open(file_path, 'wb') as out_file:
                await out_file.write(file_content)
            
            # Verify file was written
            if not file_path.exists() or file_path.stat().st_size == 0:
                errors.append(f"{file.filename}: Failed to write file")
                continue
            
            # Pixel-level image validation — confirm the file is actually decodeable
            try:
                from PIL import Image as PILImage
                with PILImage.open(file_path) as pil_img:
                    pil_img.verify()  # raises if corrupt
            except Exception:
                try:
                    file_path.unlink(missing_ok=True)
                except Exception:
                    pass
                errors.append(f"{file.filename}: Image is corrupt or unreadable (failed pixel validation)")
                continue
            
            # Add to database
            DatasetService.add_image(
                dataset_id=dataset_id,
                image_id=image_id,
                filename=new_filename,
                original_name=file.filename,
                path=str(file_path)
            )
            
            # Also keep in memory for compatibility
            image_info = {
                "id": image_id,
                "filename": new_filename,
                "original_name": file.filename,
                "path": str(file_path),
                "annotated": False,
                "split": None,  # train, val, test, or None
                "uploaded_at": datetime.now().isoformat()
            }
            
            if dataset_id not in datasets_db:
                datasets_db[dataset_id] = DatasetService.get_dataset(dataset_id) or {
                    "id": dataset_id,
                    "images": []
                }
            
            if "images" not in datasets_db[dataset_id]:
                datasets_db[dataset_id]["images"] = []
            
            datasets_db[dataset_id]["images"].append(image_info)
            uploaded_files.append(image_info)
            
        except Exception as e:
            import traceback
            error_msg = f"{file.filename if file.filename else 'Unknown file'}: {str(e)}"
            errors.append(error_msg)
            print(f"Error uploading file: {error_msg}")
            print(traceback.format_exc())
            continue
    
    datasets_db[dataset_id]["updated_at"] = datetime.now().isoformat()
    
    # Return response
    response_data = {
        "success": len(uploaded_files) > 0,
        "uploaded": len(uploaded_files),
        "files": uploaded_files
    }
    
    if errors:
        response_data["errors"] = errors
        response_data["error_count"] = len(errors)
    
    return JSONResponse(content=response_data)

@router.post("/save")
@router.post("/annotations/save")
async def save_annotation(request: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """
    Save image annotations
    """
    dataset_id = request.get("dataset_id")
    image_id = request.get("image_id")
    image_name = request.get("image_name")
    width = request.get("width")
    height = request.get("height")
    boxes = request.get("boxes", [])
    status = request.get("status", "annotated") # Default to annotated if manually saved
    split = request.get("split")
    annotation_type = request.get("annotation_type", "detection")  # 'detection' or 'classification'

    if not dataset_id or not image_id:
        raise HTTPException(status_code=400, detail="dataset_id and image_id are required")

    # Verify dataset exists and caller has annotator or higher role
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "annotator")

    # Verify image belongs to this dataset
    image_belongs = any(img["id"] == image_id for img in db_dataset.get("images", []))
    if not image_belongs:
        raise HTTPException(status_code=404, detail="Image not found in this dataset")

    # Validate class_ids are within dataset class range
    num_classes = len(db_dataset.get("classes", []))
    for box in boxes:
        cid = box.get("class_id", 0)
        if num_classes > 0 and (cid < 0 or cid >= num_classes):
            raise HTTPException(
                status_code=400,
                detail=f"class_id {cid} is out of range for this dataset ({num_classes} classes)"
            )

    # Validate split if provided
    if split and split not in ["train", "val", "test"]:
        raise HTTPException(status_code=400, detail="Split must be 'train', 'val', or 'test'")
    
    # Save to database
    annotation_id = f"{dataset_id}_{image_id}"
    success = AnnotationService.save_annotation(
        annotation_id=annotation_id,
        dataset_id=dataset_id,
        image_id=image_id,
        image_name=image_name,
        width=width,
        height=height,
        boxes=boxes,
        split=split,
        status=status
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save annotation to database")
    
    # Also keep in memory for compatibility
    annotations_db[annotation_id] = {
        "dataset_id": dataset_id,
        "image_id": image_id,
        "image_name": image_name,
        "width": width,
        "height": height,
        "boxes": boxes,
        "split": split,
        "status": status,
        "annotation_type": annotation_type,
        "updated_at": datetime.now().isoformat()
    }
    
    # Convert to YOLO format and save
    labels_dir = Path(f"datasets/{dataset_id}/labels")
    labels_dir.mkdir(exist_ok=True, parents=True)
    label_file = labels_dir / f"{Path(image_name).stem}.txt"
    
    with open(label_file, 'w') as f:
        if annotation_type == "classification":
            # Classification: store only class_id (whole-image label)
            for box in boxes:
                f.write(f"{box['class_id']}\n")
        else:
            # Detection/Segmentation
            for box in boxes:
                if width <= 0 or height <= 0:
                    continue
                
                box_type = box.get("type", "box")
                
                if box_type == "polygon" or box_type == "line":
                    points = box.get("points", [])
                    if len(points) < 2:
                        continue
                    
                    # YOLO Segmentation format: class_id x1 y1 x2 y2 ... (normalized)
                    coords = []
                    for p in points:
                        norm_x = max(0.0, min(1.0, p["x"] / width))
                        norm_y = max(0.0, min(1.0, p["y"] / height))
                        coords.extend([f"{norm_x:.6f}", f"{norm_y:.6f}"])
                    
                    f.write(f"{box['class_id']} {' '.join(coords)}\n")
                    
                elif box_type == "joint":
                    # For joints/keypoints without bbox, a proxy bbox could be used or just a point format depending on YOLO configuration
                    # Standard YOLO pose format requires a bbox. We'll make a tiny bounding box around the point.
                    # format: class_id center_x center_y width height px py visibility ...
                    center_x = max(0.0, min(1.0, box["x"] / width))
                    center_y = max(0.0, min(1.0, box["y"] / height))
                    pw = 0.02
                    ph = 0.02
                    # simple bounding box fallback
                    f.write(f"{box['class_id']} {center_x:.6f} {center_y:.6f} {pw:.6f} {ph:.6f}\n")
                    
                else:
                    # Standard Bounding Box
                    center_x = (box["x"] + box["width"] / 2) / width
                    center_y = (box["y"] + box["height"] / 2) / height
                    norm_width = box["width"] / width
                    norm_height = box["height"] / height
                    
                    center_x = max(0.0, min(1.0, center_x))
                    center_y = max(0.0, min(1.0, center_y))
                    norm_width = max(0.0, min(1.0, norm_width))
                    norm_height = max(0.0, min(1.0, norm_height))
                    
                    f.write(f"{box['class_id']} {center_x:.6f} {center_y:.6f} {norm_width:.6f} {norm_height:.6f}\n")
    
    # Update memory cache
    if dataset_id in datasets_db:
        for img in datasets_db[dataset_id].get("images", []):
            if img["id"] == image_id:
                img["annotated"] = True
                if split:
                    img["split"] = split
                break
    
    return JSONResponse(content={
        "success": True,
        "annotation_id": annotation_id,
        "label_file": str(label_file),
        "split": split,
        "annotation_type": annotation_type
    })

@router.get("/annotations/{dataset_id}/{image_id}")
async def get_annotation(
    dataset_id: str, 
    image_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get annotations for an image
    """
    # Get from database
    db_annotation = AnnotationService.get_annotation(dataset_id, image_id)
    
    if db_annotation:
        # Sync with memory
        annotations_db[db_annotation['id']] = db_annotation
        return db_annotation
    
    # Fallback to memory
    annotation_id = f"{dataset_id}_{image_id}"
    if annotation_id not in annotations_db:
        return {"boxes": []}
    
    return annotations_db[annotation_id]


async def _export_task(job_id: str, dataset_id: str, split_ratio: float, augmentations: dict, dataset: dict, annotated_images: list, images_with_split: list):
    try:
        from PIL import Image, ImageOps
        import shutil
        import zipfile
        from pathlib import Path
        
        export_jobs[job_id]["status"] = "running"
        export_jobs[job_id]["progress"] = 0
        
        dataset_dir = Path(f"datasets/{dataset_id}")
        
        if images_with_split:
            train_images = [img for img in annotated_images if img.get("split") == "train"]
            val_images = [img for img in annotated_images if img.get("split") == "val"]
            test_images = [img for img in annotated_images if img.get("split") == "test"]
            train_images.extend([img for img in annotated_images if not img.get("split")])
        else:
            import random
            random.shuffle(annotated_images)
            split_idx = int(len(annotated_images) * split_ratio)
            train_images = annotated_images[:split_idx]
            val_images = annotated_images[split_idx:]
            test_images = []
        
        train_dir = dataset_dir / "split" / "train"
        val_dir = dataset_dir / "split" / "val"
        test_dir = dataset_dir / "split" / "test"
        
        splits = [
            (train_dir, train_images, "train"),
            (val_dir, val_images, "val"),
            (test_dir, test_images, "test")
        ]
        
        total_steps = len(annotated_images)
        current_step = 0

        def _transform_label_line(line: str, flip_horizontal: bool, flip_vertical: bool) -> str:
            parts = line.strip().split()
            if not parts:
                return ""
            if len(parts) == 5:
                cls, x, y, w, h = parts[0], float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                if flip_horizontal:
                    x = 1.0 - x
                if flip_vertical:
                    y = 1.0 - y
                return f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n"
            if len(parts) >= 7 and (len(parts) % 2 == 1):
                cls = parts[0]
                coords = [float(p) for p in parts[1:]]
                for i in range(0, len(coords), 2):
                    if flip_horizontal:
                        coords[i] = 1.0 - coords[i]
                    if flip_vertical:
                        coords[i + 1] = 1.0 - coords[i + 1]
                return f"{cls} " + " ".join(f"{c:.6f}" for c in coords) + "\n"
            return line
        
        for split_dir, images, split_name in splits:
            if images:
                (split_dir / "images").mkdir(parents=True, exist_ok=True)
                (split_dir / "labels").mkdir(parents=True, exist_ok=True)
                
                for img in images:
                    src_img = dataset_dir / "images" / img["filename"]
                    dst_img = split_dir / "images" / img["filename"]
                    if src_img.exists():
                        shutil.copy2(src_img, dst_img)
                    
                    label_name = f"{Path(img['filename']).stem}.txt"
                    src_label = dataset_dir / "labels" / label_name
                    dst_label = split_dir / "labels" / label_name
                    if src_label.exists():
                        shutil.copy2(src_label, dst_label)
                    else:
                        (dst_label).write_text("")

                    if split_name == "train" and augmentations and any(augmentations.values()):
                        try:
                            with Image.open(src_img) as im:
                                if augmentations.get("flipHorizontal"):
                                    aug_filename = f"aug_hflip_{img['filename']}"
                                    aug_img_path = split_dir / "images" / aug_filename
                                    aug_label_path = split_dir / "labels" / f"{Path(aug_filename).stem}.txt"
                                    im_flipped = ImageOps.mirror(im)
                                    im_flipped.save(aug_img_path)
                                    
                                    if src_label.exists():
                                        with open(src_label, 'r') as f_src, open(aug_label_path, 'w') as f_dst:
                                            for line in f_src:
                                                f_dst.write(_transform_label_line(line, True, False))
                                    else:
                                        aug_label_path.write_text("")
                                                    
                                if augmentations.get("flipVertical"):
                                    aug_filename = f"aug_vflip_{img['filename']}"
                                    aug_img_path = split_dir / "images" / aug_filename
                                    aug_label_path = split_dir / "labels" / f"{Path(aug_filename).stem}.txt"
                                    im_flipped = ImageOps.flip(im)
                                    im_flipped.save(aug_img_path)
                                    
                                    if src_label.exists():
                                        with open(src_label, 'r') as f_src, open(aug_label_path, 'w') as f_dst:
                                            for line in f_src:
                                                f_dst.write(_transform_label_line(line, False, True))
                                    else:
                                        aug_label_path.write_text("")
                                                    
                                if augmentations.get("noise"):
                                    aug_filename = f"aug_noise_{img['filename']}"
                                    aug_img_path = split_dir / "images" / aug_filename
                                    aug_label_path = split_dir / "labels" / f"{Path(aug_filename).stem}.txt"
                                    im_noise = im.convert("L").convert("RGB")
                                    im_noise.save(aug_img_path)
                                    if src_label.exists():
                                        shutil.copy2(src_label, aug_label_path)
                                    else:
                                        aug_label_path.write_text("")
                        except Exception as e:
                            print(f"Augmentation failed for {img['filename']}: {e}")
                    
                    current_step += 1
                    export_jobs[job_id]["progress"] = int((current_step / total_steps) * 80)
        
        split_path = (dataset_dir / 'split').resolve()
        yaml_content = f"""# YOLO Dataset Configuration
# Generated from dataset: {dataset['name']}

path: {split_path}
train: train/images
val: val/images
"""
        if test_images:
            yaml_content += "test: test/images\n"
        
        yaml_content += "\n# Classes\nnames:\n"
        for idx, class_name in enumerate(dataset["classes"]):
            yaml_content += f"  {idx}: {class_name}\n"
        yaml_content += f"\nnc: {len(dataset['classes'])}\n"
        
        yaml_path = dataset_dir / "data.yaml"
        with open(yaml_path, 'w') as f:
            f.write(yaml_content)
        
        zip_path = dataset_dir / f"{dataset['name']}_export.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(yaml_path, "data.yaml")
            for split_name in ["train", "val", "test"]:
                split_path = dataset_dir / "split" / split_name
                if split_path.exists():
                    for folder in ["images", "labels"]:
                        folder_path = split_path / folder
                        if folder_path.exists():
                            for file in folder_path.iterdir():
                                if file.is_file():
                                    arcname = f"{split_name}/{folder}/{file.name}"
                                    zipf.write(file, arcname)
                                    
        export_jobs[job_id]["progress"] = 100
        export_jobs[job_id]["status"] = "completed"
        export_jobs[job_id]["yaml_path"] = str(yaml_path)
        export_jobs[job_id]["zip_path"] = str(zip_path)
        
    except Exception as e:
        logger.error(f"Export task failed: {str(e)}")
        export_jobs[job_id]["status"] = "failed"
        export_jobs[job_id]["error"] = str(e)


@router.get("/datasets/{dataset_id}/export-status/{job_id}")
async def get_export_status(dataset_id: str, job_id: str, current_user: dict = Depends(get_current_user)):
    if job_id not in export_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = export_jobs[job_id]
    if job.get("dataset_id") and job["dataset_id"] != dataset_id:
        raise HTTPException(status_code=403, detail="Job does not belong to this dataset")
    return job


@router.post("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    request: ExportRequest = Body(default_factory=ExportRequest),
    current_user: dict = Depends(get_current_user)
):
    split_ratio = request.split_ratio
    augmentations = request.config or {}

    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "admin")

    dataset = db_dataset
    dataset_dir = Path(f"datasets/{dataset_id}")
    
    all_images = DatasetService.get_dataset_images(dataset_id)
    annotated_images = list(all_images or [])
    
    if not annotated_images:
        raise HTTPException(status_code=400, detail="No images in dataset")
    
    images_with_split = [img for img in annotated_images if img.get("split")]
    
    job_id = str(uuid.uuid4())
    export_jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "dataset_id": dataset_id
    }
    
    background_tasks.add_task(
        _export_task, 
        job_id, dataset_id, split_ratio, augmentations, dataset, annotated_images, images_with_split
    )
    
    return {
        "success": True,
        "job_id": job_id,
        "message": "Export started in the background"
    }


@router.get("/datasets/{dataset_id}/download")
async def download_dataset(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Download exported dataset
    """
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "admin")

    dataset = db_dataset
    zip_path = Path(f"datasets/{dataset_id}/{dataset['name']}_export.zip")
    
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Dataset not exported yet. Export first.")
    
    return FileResponse(
        path=str(zip_path),
        filename=f"{dataset['name']}_dataset.zip",
        media_type="application/zip"
    )

@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a dataset
    """
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "owner")

    # Delete directory
    dataset_dir = Path(f"datasets/{dataset_id}")
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    
    # Remove from database
    del datasets_db[dataset_id]
    
    # Remove annotations
    keys_to_delete = [k for k in annotations_db.keys() if k.startswith(f"{dataset_id}_")]
    for key in keys_to_delete:
        del annotations_db[key]
    
    return {"success": True, "message": "Dataset deleted"}

@router.get("/datasets/{dataset_id}/stats")
async def get_dataset_stats(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get dataset statistics
    """
    # Get from database
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "viewer")

    stats = AnnotationService.get_dataset_stats(dataset_id)
    return stats

@router.put("/datasets/{dataset_id}/images/{image_id}/split")
async def update_image_split(
    dataset_id: str, 
    image_id: str, 
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the split assignment for an image
    """
    # Check if dataset exists and user has access
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "annotator")

    split = request.get("split")
    if split and split not in ["train", "val", "test"]:
        raise HTTPException(status_code=400, detail="Split must be 'train', 'val', or 'test'")
    
    # Update in database
    success = DatasetService.update_image_split(dataset_id, image_id, split)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update split in database")
    
    # Update memory cache
    if dataset_id in datasets_db:
        for img in datasets_db[dataset_id].get("images", []):
            if img["id"] == image_id:
                img["split"] = split
                break
    
    return JSONResponse(content={
        "success": True,
        "image_id": image_id,
        "split": split
    })


async def _auto_label_task(job_id: str, dataset_id: str, dataset: dict, target_images: list, model_path: str, confidence: float):
    try:
        from app.routes.inference import YOLOInference
        from PIL import Image
        import time
        from datetime import datetime
        
        auto_label_jobs[job_id]["status"] = "running"
        auto_label_jobs[job_id]["progress"] = 0
        
        local_model = YOLOInference(model_path)
        
        count = 0
        total_steps = len(target_images)
        current_step = 0
        
        for img in target_images:
            ann_id = f"{dataset_id}_{img['id']}"
            curr_ann = annotations_db.get(ann_id)
            if curr_ann and curr_ann.get("status") == "reviewed":
                current_step += 1
                auto_label_jobs[job_id]["progress"] = int((current_step / total_steps) * 100)
                continue
                
            image_path = Path(img["path"])
            if not image_path.exists():
                current_step += 1
                auto_label_jobs[job_id]["progress"] = int((current_step / total_steps) * 100)
                continue
                
            detections = local_model.predict(str(image_path), conf_threshold=confidence)
            
            boxes = []
            width = 0
            height = 0
            
            with Image.open(image_path) as pil_img:
                width, height = pil_img.size
                
            for det in detections:
                bbox = det["bbox"]
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                x = bbox[0]
                y = bbox[1]
                
                class_name = det["class_name"]
                class_id = -1
                
                if class_name in dataset["classes"]:
                    class_id = dataset["classes"].index(class_name)
                else:
                    for idx, cls in enumerate(dataset["classes"]):
                        if cls.lower() in class_name.lower():
                            class_id = idx
                            break
                
                if class_id != -1:
                    boxes.append({
                        "x": x,
                        "y": y,
                        "width": w,
                        "height": h,
                        "class_id": class_id,
                        "class_name": dataset["classes"][class_id],
                        "confidence": det["confidence"]
                    })
            
            if boxes:
                annotation_id = f"{dataset_id}_{img['id']}"
                AnnotationService.save_annotation(
                    annotation_id=annotation_id,
                    dataset_id=dataset_id,
                    image_id=img['id'],
                    image_name=img['filename'],
                    width=width,
                    height=height,
                    boxes=boxes,
                    split=img.get("split"),
                    status="predicted"
                )
                
                annotations_db[annotation_id] = {
                    "dataset_id": dataset_id,
                    "image_id": img['id'],
                    "image_name": img['filename'],
                    "width": width,
                    "height": height,
                    "boxes": boxes,
                    "split": img.get("split"),
                    "status": "predicted",
                    "updated_at": datetime.now().isoformat()
                }
                
                img["annotated"] = True
                count += 1
                
            current_step += 1
            auto_label_jobs[job_id]["progress"] = int((current_step / total_steps) * 100)
            
        auto_label_jobs[job_id]["status"] = "completed"
        auto_label_jobs[job_id]["progress"] = 100
        auto_label_jobs[job_id]["labeled_count"] = count
        
    except Exception as e:
        logger.error(f"Auto-label task failed: {str(e)}")
        auto_label_jobs[job_id]["status"] = "failed"
        auto_label_jobs[job_id]["error"] = str(e)


@router.get("/datasets/{dataset_id}/auto-label-status/{job_id}")
async def get_auto_label_status(dataset_id: str, job_id: str):
    if job_id not in auto_label_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return auto_label_jobs[job_id]


@router.post("/auto-label")
async def auto_label_images(
    background_tasks: BackgroundTasks,
    dataset_id: str = Form(...),
    image_ids: str = Form(...),
    model_name: str = Form("yolov8n.pt"),
    confidence: float = Form(0.25),
    job_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "annotator")

    dataset = db_dataset

    model_path = model_name
    if job_id:
        weights_path = Path("runs/detect") / f"job_{job_id}" / "weights" / "best.pt"
        if weights_path.exists():
            model_path = str(weights_path)
            
    target_images = []
    
    if image_ids == "all":
        target_images = [img for img in dataset.get("images", [])]
    else:
        ids = image_ids.split(",")
        target_images = [img for img in dataset.get("images", []) if img["id"] in ids]
        
    if not target_images:
        raise HTTPException(status_code=400, detail="No valid images selected for auto-labeling")
        
    task_job_id = str(uuid.uuid4())
    auto_label_jobs[task_job_id] = {
        "status": "pending",
        "progress": 0,
        "total": len(target_images)
    }
    
    background_tasks.add_task(
        _auto_label_task,
        task_job_id, dataset_id, dataset, target_images, model_path, confidence
    )
    
    return {
        "success": True,
        "job_id": task_job_id,
        "message": "Auto-labeling started in the background"
    }


@router.get("/image/{dataset_id}/{image_filename}")
async def serve_image(dataset_id: str, image_filename: str, token: Optional[str] = None):
    """
    Serve an image file.
    Accepts auth via Bearer header OR ?token= query param so <img src> tags work.
    """
    from app.core.rbac import decode_access_token
    if not token or not decode_access_token(token):
        raise HTTPException(status_code=401, detail="Authentication required to view images")

    image_path = Path(f"datasets/{dataset_id}/images/{image_filename}")
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_filename}")
    
    # Determine media type based on extension
    ext = image_filename.lower().split('.')[-1]
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    media_type = media_types.get(ext, 'image/jpeg')
    
    return FileResponse(
        path=str(image_path),
        media_type=media_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600"
        }
    )


@router.get("/datasets/{dataset_id}/download-format")
async def download_format(
    dataset_id: str,
    format: str = "yolo",
    current_user: dict = Depends(get_current_user)
):
    """
    Download dataset annotations in a specific format.
    Supported formats: yolo, coco, voc, csv, createml
    """
    from app.services.export_service import ExportService

    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _require_role(dataset_id, current_user["id"], db_dataset["user_id"], "admin")

    images = DatasetService.get_dataset_images(dataset_id)
    classes = db_dataset.get("classes", [])

    if format == "yolo":
        # Return existing YOLO export
        zip_path = Path(f"datasets/{dataset_id}/{db_dataset['name']}_export.zip")
        if not zip_path.exists():
            raise HTTPException(status_code=404, detail="YOLO export not found. Export dataset first.")
        return FileResponse(path=str(zip_path), filename=f"{db_dataset['name']}_yolo.zip", media_type="application/zip")

    elif format == "coco":
        output_path = ExportService.export_coco(dataset_id, images, [], classes)
        return FileResponse(path=output_path, filename=f"{db_dataset['name']}_coco.json", media_type="application/json")

    elif format == "voc":
        output_path = ExportService.export_voc(dataset_id, images, classes)
        return FileResponse(path=output_path, filename=f"{db_dataset['name']}_voc.zip", media_type="application/zip")

    elif format == "csv":
        output_path = ExportService.export_csv(dataset_id, images, classes)
        return FileResponse(path=output_path, filename=f"{db_dataset['name']}_annotations.csv", media_type="text/csv")

    elif format == "createml":
        output_path = ExportService.export_createml(dataset_id, images, classes)
        return FileResponse(path=output_path, filename=f"{db_dataset['name']}_createml.json", media_type="application/json")

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Use: yolo, coco, voc, csv, createml")