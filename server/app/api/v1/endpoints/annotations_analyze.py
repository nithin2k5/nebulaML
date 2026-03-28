from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pathlib import Path
import sys
import logging
from dataclasses import asdict

# Add parent directory to path for imports
# sys.path.append(str(Path(__file__).parent.parent.parent))
from app.services.dataset_analyzer import DatasetAnalyzer
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/datasets/{dataset_id}/analyze")
async def analyze_dataset(dataset_id: str, current_user: dict = Depends(get_current_user)):
    """
    Perform comprehensive dataset analysis for training readiness
    Returns analysis including:
    - Class distribution
    - Object size/aspect ratio analysis
    - Quality metrics (including image quality, per-class, near-duplicates)
    - Training recommendations
    - Warnings and issues
    """
    try:
        from app.services.database import DatasetService, QualitySnapshotService
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if dataset.get("user_id") and dataset["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this dataset")

        analysis = DatasetAnalyzer.analyze_dataset(dataset_id)

        # Convert dataclass to dict for JSON serialization
        result = asdict(analysis)

        # Persist snapshot for trend tracking (non-blocking — failure is silent)
        try:
            QualitySnapshotService.save_snapshot(dataset_id, result)
        except Exception as snap_err:
            logger.warning(f"Failed to save quality snapshot: {snap_err}")

        return JSONResponse(content={
            "success": True,
            "analysis": result
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        logger.error(f"Error analyzing dataset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}/quality-history")
async def get_quality_history(
    dataset_id: str,
    limit: int = 30,
    current_user: dict = Depends(get_current_user),
):
    """Return historical quality scores for a dataset (for trend charts)."""
    try:
        from app.services.database import DatasetService, QualitySnapshotService
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if dataset.get("user_id") and dataset["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this dataset")

        history = QualitySnapshotService.get_history(dataset_id, min(limit, 100))
        return JSONResponse(content={"success": True, "history": history})
    except Exception as e:
        logger.error(f"Error fetching quality history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/datasets/{dataset_id}/uncertainty")
async def analyze_uncertainty(dataset_id: str, current_user: dict = Depends(get_current_user)):
    """
    Analyze unlabeled images and return them sorted by uncertainty (active learning).
    Uncertainty is calculated as 1.0 - max_confidence.
    """
    try:
        from app.services.database import DatasetService
        from app.services.inference import YOLOInference
        import os

        # Get dataset and verify ownership
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if dataset.get("user_id") and dataset["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this dataset")
        
        # Get all images
        all_images = DatasetService.get_dataset_images(dataset_id)
        
        # Filter for unlabeled images
        unlabeled_images = [img for img in all_images if not img.get("annotated", False)]
        
        if not unlabeled_images:
            return JSONResponse(content={"success": True, "images": []})
            
        # Initialize model (use best available or default)
        model_name = "yolov8n.pt" # Default
        
        try:
            model = YOLOInference(model_name)
        except Exception as e:
            logger.warning(f"Failed to load model {model_name}, using default: {e}")
            model = YOLOInference("yolov8n.pt")

        datasets_dir = Path("datasets") / dataset_id / "images"
        
        scored_images = []
        
        # Limit to batch size for responsiveness
        # In production, this should be a background task or paginated
        batch_images = unlabeled_images[:50] 
        
        for img in batch_images:
            img_path = datasets_dir / img["filename"]
            if not img_path.exists():
                continue
                
            # Run inference
            results = model.predict(str(img_path), conf_threshold=0.25)
            
            # Calculate uncertainty: 1.0 - max_confidence
            if not results:
                # No detections = high uncertainty (or high certainty it's empty?)
                # For active learning, we typically want to check "hard" cases.
                uncertainty = 1.0
            else:
                max_conf = max([r.get("confidence", 0) for r in results])
                uncertainty = 1.0 - max_conf
                
            scored_images.append({
                **img,
                "uncertainty_score": round(uncertainty, 4),
                "detections_count": len(results)
            })
            
        # Sort by uncertainty (descending) -> highest uncertainty first
        scored_images.sort(key=lambda x: x["uncertainty_score"], reverse=True)
        
        return JSONResponse(content={
            "success": True, 
            "images": scored_images,
            "total_unlabeled": len(unlabeled_images),
            "analyzed_count": len(batch_images)
        })

    except Exception as e:
        logger.error(f"Error analyzing uncertainty: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

