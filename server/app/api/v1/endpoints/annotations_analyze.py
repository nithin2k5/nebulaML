from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pathlib import Path
import sys
import logging
from dataclasses import asdict

from app.services.dataset_analyzer import DatasetAnalyzer
from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.services.database import DatasetService, QualitySnapshotService

router = APIRouter()
logger = logging.getLogger(__name__)

def run_analysis_task(dataset_id: str):
    """Background task to run heavy dataset analysis and save snapshot."""
    try:
        logger.info(f"Starting background analysis for {dataset_id}")
        analysis = DatasetAnalyzer.analyze_dataset(dataset_id)
        result = asdict(analysis)
        QualitySnapshotService.save_snapshot(dataset_id, result)
        logger.info(f"Finished background analysis for {dataset_id}")
    except Exception as e:
        logger.error(f"Background analysis failed for {dataset_id}: {e}", exc_info=True)

@router.get("/datasets/{dataset_id}/analyze")
async def analyze_dataset(
    dataset_id: str, 
    background_tasks: BackgroundTasks,
    force_refresh: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """
    Perform comprehensive dataset analysis for training readiness
    Returns cached analysis if available and recent, or kicks off a background task.
    """
    try:
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        require_role(dataset_id, current_user["id"], dataset["user_id"], "annotator")

        # Try to get latest snapshot
        latest = QualitySnapshotService.get_latest_snapshot(dataset_id)
        
        if latest and not force_refresh:
            return JSONResponse(content={
                "success": True,
                "status": "completed",
                "analysis": latest
            })
            
        # We need to run it. Kick off background task
        background_tasks.add_task(run_analysis_task, dataset_id)
        
        return JSONResponse(content={
            "success": True,
            "status": "processing",
            "message": "Analysis started in background"
        })

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        logger.error(f"Error starting dataset analysis: {e}", exc_info=True)
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
        require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")

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

        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")
        
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

