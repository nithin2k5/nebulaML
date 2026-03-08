from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Body, Depends
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

router = APIRouter()
logger = logging.getLogger(__name__)

# Keep in-memory storage as fallback/backup
annotations_db: Dict[str, Dict] = {}
datasets_db: Dict[str, Dict] = {}

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
    List all datasets
    """
    # Get from database
    db_datasets = DatasetService.list_datasets(user_id=current_user["id"])
    
    # Also sync with memory for compatibility
    for db_dataset in db_datasets:
        datasets_db[db_dataset['id']] = db_dataset
    
    return {
        "datasets": db_datasets
    }

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
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
    
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
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
    
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
@router.post("/annotations/save")  # Legacy alias to handle potential caching/old frontend
async def save_annotation(request: dict = Body(...)):
    """
    Save image annotations
    """
    dataset_id = request.get("dataset_id")
    
    # Check authorization first
    try:
        from app.api.v1.endpoints.auth import get_current_user, security
        # We need to manually extract the user here or change this to depend on current user
        # Note: Depending on current_user via dependency injection is better, but since
        # this endpoint was written flexibly, let's keep it functionally sound.
        # As it has @router.post, let's just make the changes to the def directly.
    except Exception as e:
        pass
    
    image_id = request.get("image_id")
    image_name = request.get("image_name")
    width = request.get("width")
    height = request.get("height")
    boxes = request.get("boxes", [])
    status = request.get("status", "annotated") # Default to annotated if manually saved
    split = request.get("split")

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
        "updated_at": datetime.now().isoformat()
    }
    
    # Convert to YOLO format and save
    labels_dir = Path(f"datasets/{dataset_id}/labels")
    labels_dir.mkdir(exist_ok=True, parents=True)
    label_file = labels_dir / f"{Path(image_name).stem}.txt"
    
    with open(label_file, 'w') as f:
        for box in boxes:
            # Convert to YOLO format (class_id center_x center_y width height)
            if width <= 0 or height <= 0:
                continue
                
            # Normalize coordinates to 0-1
            center_x = (box["x"] + box["width"] / 2) / width
            center_y = (box["y"] + box["height"] / 2) / height
            norm_width = box["width"] / width
            norm_height = box["height"] / height
            
            # Clamp values to 0-1 range to be safe
            center_x = max(0.0, min(1.0, center_x))
            center_y = max(0.0, min(1.0, center_y))
            norm_width = max(0.0, min(1.0, norm_width))
            norm_height = max(0.0, min(1.0, norm_height))
            
            f.write(f"{box['class_id']} {center_x} {center_y} {norm_width} {norm_height}\n")
    
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
        "split": split
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

@router.post("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: str, 
    request: ExportRequest = Body(default_factory=ExportRequest),
    current_user: dict = Depends(get_current_user)
):
    """
    Export dataset in YOLO format with train/val/test split and optional augmentations.
    Config example: {"flipHorizontal": true, "flipVertical": false, "noise": true}
    """
    
    split_ratio = request.split_ratio
    augmentations = request.config or {}

    # Get dataset from database
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
         
    dataset = db_dataset
    
    dataset_dir = Path(f"datasets/{dataset_id}")
    
    # Get all annotated images from database
    all_images = DatasetService.get_dataset_images(dataset_id)
    annotated_images = [img for img in all_images if img.get("annotated", False)]
    
    if not annotated_images:
        raise HTTPException(status_code=400, detail="No annotated images in dataset")
    
    # Check if images have manually assigned splits
    images_with_split = [img for img in annotated_images if img.get("split")]
    
    if images_with_split:
        # Use manually assigned splits
        train_images = [img for img in annotated_images if img.get("split") == "train"]
        val_images = [img for img in annotated_images if img.get("split") == "val"]
        test_images = [img for img in annotated_images if img.get("split") == "test"]
        # Images without split go to train by default
        train_images.extend([img for img in annotated_images if not img.get("split")])
    else:
        # Use automatic split based on ratio
        import random
        random.shuffle(annotated_images)
        split_idx = int(len(annotated_images) * split_ratio)
        train_images = annotated_images[:split_idx]
        val_images = annotated_images[split_idx:]
        test_images = []
    
    # Create train/val/test directories
    train_dir = dataset_dir / "split" / "train"
    val_dir = dataset_dir / "split" / "val"
    test_dir = dataset_dir / "split" / "test"
    
    splits = [
        (train_dir, train_images, "train"),
        (val_dir, val_images, "val"),
        (test_dir, test_images, "test")
    ]
    
    for split_dir, images, split_name in splits:
        if images:  # Only create directory if there are images
            (split_dir / "images").mkdir(parents=True, exist_ok=True)
            (split_dir / "labels").mkdir(parents=True, exist_ok=True)
            
            for img in images:
                # Copy image
                src_img = dataset_dir / "images" / img["filename"]
                dst_img = split_dir / "images" / img["filename"]
                if src_img.exists():
                    shutil.copy2(src_img, dst_img)
                
                # Copy label
                label_name = f"{Path(img['filename']).stem}.txt"
                src_label = dataset_dir / "labels" / label_name
                dst_label = split_dir / "labels" / label_name
                if src_label.exists():
                    shutil.copy2(src_label, dst_label)

                # --- AUGMENTATIONS (Training Set Only) ---
                if split_name == "train" and augmentations and any(augmentations.values()):
                    try:
                        # Load original image
                        with Image.open(src_img) as im:
                            # 1. Horizontal Flip
                            if augmentations.get("flipHorizontal"):
                                aug_filename = f"aug_hflip_{img['filename']}"
                                aug_img_path = split_dir / "images" / aug_filename
                                aug_label_path = split_dir / "labels" / f"{Path(aug_filename).stem}.txt"
                                
                                # Flip Image
                                im_flipped = ImageOps.mirror(im)
                                im_flipped.save(aug_img_path)
                                
                                # Flip Label (x_center = 1 - x_center)
                                if src_label.exists():
                                    with open(src_label, 'r') as f_src, open(aug_label_path, 'w') as f_dst:
                                        for line in f_src:
                                            parts = line.strip().split()
                                            if len(parts) >= 5:
                                                cls, x, y, w, h = parts[0], float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                                                new_x = 1.0 - x
                                                f_dst.write(f"{cls} {new_x} {y} {w} {h}\n")
                                                
                            # 2. Vertical Flip
                            if augmentations.get("flipVertical"):
                                aug_filename = f"aug_vflip_{img['filename']}"
                                aug_img_path = split_dir / "images" / aug_filename
                                aug_label_path = split_dir / "labels" / f"{Path(aug_filename).stem}.txt"
                                
                                # Flip Image
                                im_flipped = ImageOps.flip(im)
                                im_flipped.save(aug_img_path)
                                
                                # Flip Label (y_center = 1 - y_center)
                                if src_label.exists():
                                    with open(src_label, 'r') as f_src, open(aug_label_path, 'w') as f_dst:
                                        for line in f_src:
                                            parts = line.strip().split()
                                            if len(parts) >= 5:
                                                cls, x, y, w, h = parts[0], float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                                                new_y = 1.0 - y
                                                f_dst.write(f"{cls} {x} {new_y} {w} {h}\n")
                                                
                            # 3. Noise/Blur (Grayscale for noise in this basic impl)
                            if augmentations.get("noise"):
                                aug_filename = f"aug_noise_{img['filename']}"
                                aug_img_path = split_dir / "images" / aug_filename
                                aug_label_path = split_dir / "labels" / f"{Path(aug_filename).stem}.txt"
                                
                                # Apply effect
                                im_noise = im.convert("L").convert("RGB") # Simple grayscale
                                im_noise.save(aug_img_path)
                                
                                # Copy Label directly (no coordinate change)
                                if src_label.exists():
                                    shutil.copy2(src_label, aug_label_path)
                                    
                    except Exception as e:
                        print(f"Augmentation failed for {img['filename']}: {e}")

    
    # Create data.yaml
    split_path = (dataset_dir / 'split').resolve()
    yaml_content = f"""# YOLO Dataset Configuration
# Generated from dataset: {dataset['name']}

path: {split_path}
train: train/images
val: val/images
"""
    
    # Add test if there are test images
    if test_images:
        yaml_content += "test: test/images\n"
    
    yaml_content += "\n# Classes\nnames:\n"
    for idx, class_name in enumerate(dataset["classes"]):
        yaml_content += f"  {idx}: {class_name}\n"
    
    yaml_content += f"\nnc: {len(dataset['classes'])}\n"
    
    yaml_path = dataset_dir / "data.yaml"
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    # Create zip file
    zip_path = dataset_dir / f"{dataset['name']}_export.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add data.yaml
        zipf.write(yaml_path, "data.yaml")
        
        # Add all files
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
    
    return {
        "success": True,
        "yaml_path": str(yaml_path),
        "train_images": len(train_images),
        "val_images": len(val_images),
        "test_images": len(test_images),
        "total_classes": len(dataset["classes"]),
        "zip_path": str(zip_path),
        "used_manual_splits": len(images_with_split) > 0
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
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
    
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
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
    
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
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
         
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
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
    
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

@router.post("/annotations/auto-label")
async def auto_label_images(
    dataset_id: str = Form(...),
    image_ids: str = Form(...),  # Comma-separated or "all"
    model_name: str = Form("yolov8n.pt"),
    confidence: float = Form(0.25),
    job_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Auto-label images using a pre-trained model
    """
    from app.routes.inference import inference_model, YOLOInference
    
    db_dataset = DatasetService.get_dataset(dataset_id)
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    if db_dataset.get("user_id") and db_dataset["user_id"] != current_user["id"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
         
    dataset = db_dataset

    # Initialize model if needed (reusing inference logic)
    model_path = model_name
    if job_id:
        weights_path = Path("runs/detect") / f"job_{job_id}" / "weights" / "best.pt"
        if weights_path.exists():
            model_path = str(weights_path)
            
    # We create a temporary local inference instance to avoid global state conflicts
    # In prod, this should use a worker queue
    local_model = YOLOInference(model_path)
    
    # Get images to label
    target_images = []
    
    if image_ids == "all":
        target_images = [img for img in dataset.get("images", [])] # All images
    else:
        ids = image_ids.split(",")
        target_images = [img for img in dataset.get("images", []) if img["id"] in ids]
        
    count = 0
    for img in target_images:
        # Skip if already reviewed
        # Check current annotation status
        ann_id = f"{dataset_id}_{img['id']}"
        curr_ann = annotations_db.get(ann_id)
        if curr_ann and curr_ann.get("status") == "reviewed":
            continue
            
        image_path = Path(img["path"])
        if not image_path.exists():
            continue
            
        # Run inference
        detections = local_model.predict(str(image_path), conf_threshold=confidence)
        
        # Convert detections to BoundingBox format
        boxes = []
        width = 0
        height = 0
        
        # Get image dimensions
        with Image.open(image_path) as pil_img:
            width, height = pil_img.size
            
        for det in detections:
            # YOLOInference returns xyxy and xywhn
            # BoundingBox needs x, y, width, height (pixel coords)
            # We use the absolute bbox from xyxy to calculate x,y,w,h in user format
            # User format seems to be top-left x,y and w,h (based on how it's saved)
            
            bbox = det["bbox"] # [x1, y1, x2, y2]
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = bbox[0]
            y = bbox[1]
            
            # Find class index
            class_name = det["class_name"]
            class_id = -1
            if class_name in dataset["classes"]:
                class_id = dataset["classes"].index(class_name)
            else:
                # Try to map COCO classes to dataset classes if generic model
                # This is a simple heuristic matching
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
            # Save annotation with status="predicted"
            annotation_id = f"{dataset_id}_{img['id']}"
            
            # Update DB
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
            
            # Update Memory
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
            
            # Update Image status
            img["annotated"] = True
            count += 1

    return {"success": True, "labeled_count": count}

@router.get("/image/{dataset_id}/{image_filename}")
async def serve_image(dataset_id: str, image_filename: str):
    """
    Serve an image file directly
    """
    # Construct the file path
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