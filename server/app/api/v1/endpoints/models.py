from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Dict

from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

def get_safe_model_dir(model_name: str) -> Path:
    """Securely resolve the model directory, preventing path traversal."""
    base_dir = Path("runs/detect").resolve()
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
    models_dir = Path("runs/detect")
    
    if not models_dir.exists():
        return {"models": []}
    
    models = []
    for run_dir in models_dir.iterdir():
        if run_dir.is_dir():
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
async def download_model(model_name: str, current_user: dict = Depends(get_current_user)):
    """
    Download a trained model
    """
    model_dir = get_safe_model_dir(model_name)
    model_path = model_dir / "weights" / "best.pt"
    
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="Model not found")
    
    return FileResponse(
        path=str(model_path),
        filename=f"{model_name}_best.pt",
        media_type="application/octet-stream"
    )

@router.delete("/delete/{model_name}")
async def delete_model(model_name: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a trained model
    """
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
            print(f"Error parsing metrics: {e}")
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



