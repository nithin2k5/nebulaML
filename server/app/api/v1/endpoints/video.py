"""
Video Frame Extraction Endpoint

Accepts video files (MP4, MOV, AVI) and extracts frames at configurable intervals.
Frames are saved as images in the dataset's image folder and registered in the database.
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import cv2
import uuid
import os
import tempfile
from pathlib import Path
import logging

from app.services.database import DatasetService
from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/extract-frames")
async def extract_frames(
    file: UploadFile = File(...),
    dataset_id: str = Form(...),
    frame_interval: int = Form(30),
    max_frames: int = Form(500),
    current_user: dict = Depends(get_current_user)
):
    """
    Extract frames from an uploaded video and add them to a dataset.

    - **file**: Video file (MP4, MOV, AVI, MKV)
    - **dataset_id**: Target dataset ID
    - **frame_interval**: Extract every Nth frame (default: 30 ≈ 1 per second at 30fps)
    - **max_frames**: Maximum number of frames to extract (default: 500)
    """
    # Validate file type
    allowed_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format '{ext}'. Allowed: {', '.join(allowed_extensions)}"
        )

    # Verify dataset exists and caller has annotator+ access
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "annotator")

    # Create images directory for dataset
    images_dir = Path(f"datasets/{dataset_id}/images")
    images_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded video to a temp file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Open video with OpenCV
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Failed to open video file")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        duration = total_frames / fps if fps > 0 else 0

        extracted = []
        frame_idx = 0
        count = 0

        while count < max_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            # Generate unique filename
            image_id = str(uuid.uuid4())[:8]
            frame_filename = f"frame_{frame_idx:06d}_{image_id}.jpg"
            frame_path = images_dir / frame_filename

            # Save frame as JPEG
            cv2.imwrite(str(frame_path), frame)

            # Register in database
            try:
                DatasetService.add_image(
                    dataset_id=dataset_id,
                    image_id=image_id,
                    filename=frame_filename,
                    original_name=f"{file.filename}_frame_{frame_idx}",
                    path=str(frame_path)
                )
                extracted.append({
                    "image_id": image_id,
                    "filename": frame_filename,
                    "frame_number": frame_idx,
                    "timestamp": round(frame_idx / fps, 2) if fps > 0 else 0
                })
                count += 1
            except Exception as e:
                logger.warning(f"Failed to register frame {frame_idx}: {e}")

            frame_idx += frame_interval

        cap.release()

        return JSONResponse(content={
            "success": True,
            "dataset_id": dataset_id,
            "video_info": {
                "filename": file.filename,
                "total_frames": total_frames,
                "fps": round(fps, 2),
                "duration_seconds": round(duration, 2)
            },
            "extraction": {
                "frame_interval": frame_interval,
                "frames_extracted": count,
                "frames": extracted[:20]  # Return first 20 only to keep response small
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Video extraction failed: {str(e)}")
    finally:
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
