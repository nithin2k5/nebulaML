"""
Production Monitoring Endpoint

Tracks inference results, confidence trends, and basic drift detection
for deployed models.
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory inference log storage (production would use DB)
inference_logs: Dict[str, List[Dict]] = defaultdict(list)


class InferenceLog(BaseModel):
    dataset_id: str
    model_job_id: Optional[str] = None
    model_name: Optional[str] = None
    image_name: str
    detections: List[Dict[str, Any]]
    confidence_scores: List[float]
    num_detections: int
    inference_time_ms: Optional[float] = None


@router.post("/log")
async def log_inference(
    log: InferenceLog,
    current_user: dict = Depends(get_current_user)
):
    """
    Log an inference result for monitoring.
    Called automatically after each prediction. Requires authentication.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model_job_id": log.model_job_id,
        "model_name": log.model_name,
        "image_name": log.image_name,
        "num_detections": log.num_detections,
        "confidence_scores": log.confidence_scores,
        "avg_confidence": sum(log.confidence_scores) / len(log.confidence_scores) if log.confidence_scores else 0,
        "class_counts": {},
        "inference_time_ms": log.inference_time_ms
    }

    # Count class occurrences
    for det in log.detections:
        cls_name = det.get("class", det.get("class_name", "unknown"))
        entry["class_counts"][cls_name] = entry["class_counts"].get(cls_name, 0) + 1

    inference_logs[log.dataset_id].append(entry)

    # Keep only last 10000 logs per dataset
    if len(inference_logs[log.dataset_id]) > 10000:
        inference_logs[log.dataset_id] = inference_logs[log.dataset_id][-10000:]

    return {"success": True, "logged": True}



@router.get("/stats/{dataset_id}")
async def get_monitoring_stats(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get aggregated monitoring statistics for a dataset.
    """
    logs = inference_logs.get(dataset_id, [])

    if not logs:
        return {
            "dataset_id": dataset_id,
            "total_inferences": 0,
            "avg_confidence": 0,
            "avg_detections_per_image": 0,
            "class_distribution": {},
            "confidence_trend": [],
            "recent_predictions": []
        }

    # Aggregate stats
    total = len(logs)
    all_confidences = []
    all_detections = []
    class_dist = defaultdict(int)

    for log in logs:
        all_confidences.extend(log.get("confidence_scores", []))
        all_detections.append(log.get("num_detections", 0))
        for cls_name, count in log.get("class_counts", {}).items():
            class_dist[cls_name] += count

    avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0
    avg_detections = sum(all_detections) / len(all_detections) if all_detections else 0

    # Compute confidence trend (group by batches of 10)
    batch_size = max(1, total // 20)
    confidence_trend = []
    for i in range(0, total, batch_size):
        batch = logs[i:i + batch_size]
        batch_confs = []
        for log in batch:
            batch_confs.extend(log.get("confidence_scores", []))
        if batch_confs:
            confidence_trend.append({
                "batch_index": len(confidence_trend),
                "avg_confidence": round(sum(batch_confs) / len(batch_confs), 4),
                "num_inferences": len(batch),
                "timestamp": batch[-1].get("timestamp", "")
            })

    return {
        "dataset_id": dataset_id,
        "total_inferences": total,
        "avg_confidence": round(avg_confidence, 4),
        "avg_detections_per_image": round(avg_detections, 2),
        "class_distribution": dict(class_dist),
        "confidence_trend": confidence_trend,
        "recent_predictions": logs[-10:][::-1]  # Last 10, most recent first
    }


@router.get("/drift/{dataset_id}")
async def check_drift(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Basic drift detection: compare class distribution in recent predictions
    vs older predictions. Flags significant distribution shifts.
    """
    logs = inference_logs.get(dataset_id, [])

    if len(logs) < 20:
        return {
            "dataset_id": dataset_id,
            "drift_detected": False,
            "message": "Not enough data for drift detection (need at least 20 inferences)",
            "details": {}
        }

    # Split logs into two halves
    mid = len(logs) // 2
    old_logs = logs[:mid]
    new_logs = logs[mid:]

    # Calculate class distributions
    old_dist = defaultdict(int)
    new_dist = defaultdict(int)
    old_total = 0
    new_total = 0

    for log in old_logs:
        for cls, count in log.get("class_counts", {}).items():
            old_dist[cls] += count
            old_total += count

    for log in new_logs:
        for cls, count in log.get("class_counts", {}).items():
            new_dist[cls] += count
            new_total += count

    # Compare distributions
    all_classes = set(list(old_dist.keys()) + list(new_dist.keys()))
    drift_details = {}
    max_shift = 0

    for cls in all_classes:
        old_pct = (old_dist.get(cls, 0) / old_total * 100) if old_total > 0 else 0
        new_pct = (new_dist.get(cls, 0) / new_total * 100) if new_total > 0 else 0
        shift = abs(new_pct - old_pct)
        max_shift = max(max_shift, shift)

        drift_details[cls] = {
            "old_percentage": round(old_pct, 2),
            "new_percentage": round(new_pct, 2),
            "shift": round(shift, 2),
            "direction": "increased" if new_pct > old_pct else "decreased"
        }

    # Calculate average confidence shift
    old_confs = []
    new_confs = []
    for log in old_logs:
        old_confs.extend(log.get("confidence_scores", []))
    for log in new_logs:
        new_confs.extend(log.get("confidence_scores", []))

    old_avg_conf = sum(old_confs) / len(old_confs) if old_confs else 0
    new_avg_conf = sum(new_confs) / len(new_confs) if new_confs else 0
    conf_shift = new_avg_conf - old_avg_conf

    # Drift is detected if any class shifts more than 15% or confidence drops by more than 10%
    drift_detected = max_shift > 15 or conf_shift < -0.10

    return {
        "dataset_id": dataset_id,
        "drift_detected": drift_detected,
        "severity": "high" if max_shift > 25 or conf_shift < -0.20 else "medium" if drift_detected else "low",
        "confidence_shift": round(conf_shift, 4),
        "old_avg_confidence": round(old_avg_conf, 4),
        "new_avg_confidence": round(new_avg_conf, 4),
        "max_class_shift": round(max_shift, 2),
        "class_details": drift_details,
        "recommendation": (
            "Consider re-training your model with more recent data."
            if drift_detected else
            "Model performance appears stable."
        )
    }


@router.delete("/clear/{dataset_id}")
async def clear_monitoring_data(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Clear all monitoring data for a dataset."""
    inference_logs.pop(dataset_id, None)
    return {"success": True, "message": "Monitoring data cleared"}
