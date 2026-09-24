from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Dict, Optional

from app.api.v1.endpoints.auth import get_current_user
from app.services.database import TrainingJobService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

_SERVER_ROOT = Path(__file__).resolve().parents[4]
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

# Trained runs are written to runs/detect/job_<job_id> (training.py), and
# training_jobs carries the user_id. The filesystem itself records no owner, so
# every model endpoint has to resolve the name back to a job to answer
# "is this yours?". A directory whose name does not follow that convention, or
# whose job row is gone, has no resolvable owner — treated as admin-only rather
# than as public, so an unrecognised layout fails closed.
_RUN_PREFIX = "job_"


def _owner_of_model(model_name: str) -> Optional[int]:
    """user_id that owns this run directory, or None when unresolvable."""
    if not model_name.startswith(_RUN_PREFIX):
        return None
    return TrainingJobService.get_job_owner(model_name[len(_RUN_PREFIX):])


def _require_model_access(model_name: str, current_user: dict) -> None:
    """Raise 404 unless the caller owns this model (or is an admin).

    404 rather than 403 on purpose: the model list is already filtered, so
    confirming that a name exists but belongs to someone else would hand back
    exactly what the filtering is there to withhold.
    """
    if current_user.get("role") == "admin":
        return
    owner = _owner_of_model(model_name)
    if owner is None or owner != current_user.get("id"):
        raise HTTPException(status_code=404, detail="Model not found")


def get_safe_model_dir(model_name: str) -> Path:
    """Securely resolve the model directory, preventing path traversal."""
    base_dir = _RUNS_BASE
    model_dir = (base_dir / model_name).resolve()
    
    try:
        # Ensure the resolved path is inside the base directory
        model_dir.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid model name (path traversal detected)")
        
    if model_dir == base_dir:
        raise HTTPException(status_code=400, detail="Invalid model name")
        
    return model_dir

@router.get("/list")
async def list_models(current_user: dict = Depends(get_current_user)):
    """
    List all available trained models
    """
    models_dir = _RUNS_BASE
    
    if not models_dir.exists():
        return {"models": []}
    
    # This used to walk the whole directory and hand every model on the box to
    # every signed-in user. Resolve ownership once, in bulk, rather than a
    # query per directory.
    is_admin = current_user.get("role") == "admin"
    own_job_ids = (
        set() if is_admin
        else TrainingJobService.get_job_ids_for_user(current_user["id"])
    )

    models = []
    for run_dir in models_dir.iterdir():
        if not run_dir.is_dir():
            continue
        if not is_admin:
            if not run_dir.name.startswith(_RUN_PREFIX):
                continue
            if run_dir.name[len(_RUN_PREFIX):] not in own_job_ids:
                continue
        weights_dir = run_dir / "weights"
        if weights_dir.exists():
            best_model = weights_dir / "best.pt"
            if best_model.exists():
                models.append({
                    "name": run_dir.name,
                    "path": str(best_model),
                    "size": best_model.stat().st_size,
                    "created": best_model.stat().st_mtime
                })

    return {"models": models}

@router.get("/download/{model_name}")
async def download_model(model_name: str, format: str = "pt", current_user: dict = Depends(get_current_user)):
    """
    Download a trained model
    """
    _require_model_access(model_name, current_user)
    model_dir = get_safe_model_dir(model_name)
    weights_dir = model_dir / "weights"
    
    if format == "pt":
        target_path = weights_dir / "best.pt"
    elif format == "onnx":
        target_path = weights_dir / "best.onnx"
    elif format == "engine":
        target_path = weights_dir / "best.engine"
    elif format == "coreml":
        target_path = weights_dir / "best.mlpackage"
    elif format == "tflite":
        target_path = weights_dir / "best_saved_model"
    else:
        target_path = weights_dir / f"best.{format}"
        
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Model format '{format}' not found. Export it first.")
        
    if target_path.is_dir():
        import shutil
        zip_path = weights_dir / f"best_{format}.zip"
        if not zip_path.exists():
            shutil.make_archive(str(zip_path).replace('.zip', ''), 'zip', str(target_path))
        return FileResponse(
            path=str(zip_path),
            filename=f"{model_name}_{format}.zip",
            media_type="application/zip"
        )
    
    return FileResponse(
        path=str(target_path),
        filename=f"{model_name}_{target_path.name}",
        media_type="application/octet-stream"
    )

@router.delete("/delete/{model_name}")
async def delete_model(model_name: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a trained model
    """
    _require_model_access(model_name, current_user)
    model_dir = get_safe_model_dir(model_name)
    
    if not model_dir.exists():
        raise HTTPException(status_code=404, detail="Model not found")
    
    import shutil
    shutil.rmtree(model_dir)
    
    return {"success": True, "message": f"Model {model_name} deleted"}

@router.get("/info/{model_name}")
async def get_model_info(model_name: str, current_user: dict = Depends(get_current_user)):
    """
    Get detailed information about a model
    """
    _require_model_access(model_name, current_user)
    model_dir = get_safe_model_dir(model_name)
    
    if not model_dir.exists():
        raise HTTPException(status_code=404, detail="Model not found")
    
    weights_dir = model_dir / "weights"
    best_model = weights_dir / "best.pt"
    
    # Check for results
    results_file = model_dir / "results.csv"
    
    metrics = {}
    if results_file.exists():
        try:
            import pandas as pd
            df = pd.read_csv(results_file)
            df.columns = [c.strip() for c in df.columns]
            
            # Get the best epoch based on mAP50-95
            best_idx = df['metrics/mAP50-95(B)'].idxmax() if 'metrics/mAP50-95(B)' in df.columns else -1
            
            if best_idx >= 0:
                best_row = df.iloc[best_idx]
                metrics = {
                    "precision": float(best_row.get('metrics/precision(B)', 0)),
                    "recall": float(best_row.get('metrics/recall(B)', 0)),
                    "mAP50": float(best_row.get('metrics/mAP50(B)', 0)),
                    "mAP50_95": float(best_row.get('metrics/mAP50-95(B)', 0)),
                    "fitness": float(best_row.get('fitness', 0)),
                    "best_epoch": int(best_row.get('epoch', best_idx + 1))
                }
        except Exception as e:
            logger.error(f"Error parsing metrics: {e}")
            metrics = {"error": "Failed to parse metrics file"}
            
    # Try to load args.yaml for config details
    args_file = model_dir / "args.yaml"
    config = {}
    if args_file.exists():
        try:
            import yaml
            with open(args_file, 'r') as f:
                config = yaml.safe_load(f)
        except Exception:
            pass
            
    info = {
        "name": model_name,
        "model_path": str(best_model) if best_model.exists() else None,
        "has_results": results_file.exists(),
        "created": best_model.stat().st_mtime if best_model.exists() else None,
        "size_mb": round(best_model.stat().st_size / (1024 * 1024), 2) if best_model.exists() else None,
        "metrics": metrics,
        "training_config": {
            "epochs": config.get("epochs"),
            "imgsz": config.get("imgsz"),
            "batch": config.get("batch"),
            "model": config.get("model")
        } if config else None
    }
    
    return info

@router.post("/export/{model_name}")
async def export_model(model_name: str, format: str = "onnx", current_user: dict = Depends(get_current_user)):
    """
    Export a trained model to a different format (e.g., onnx, engine, openvino, coreml, torchscript)
    """
    _require_model_access(model_name, current_user)
    model_dir = get_safe_model_dir(model_name)

    # Whitelist export formats
    allowed_formats = {"onnx", "torchscript", "openvino", "coreml", "engine", "tflite", "paddle", "ncnn"}
    if format not in allowed_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Allowed: {sorted(allowed_formats)}")

    model_path = model_dir / "weights" / "best.pt"
    
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="Model not found")
        
    try:
        from ultralytics import YOLO
        
        # Load the model
        model = YOLO(str(model_path))
        
        # Export the model
        # YOLO export returns the string path of the exported model
        exported_path = model.export(format=format)
        
        return {
            "success": True, 
            "message": f"Model exported successfully to {format}",
            "exported_path": str(exported_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")



