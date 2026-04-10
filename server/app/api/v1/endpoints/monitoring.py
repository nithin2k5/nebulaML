"""
Production Monitoring Endpoint

Tracks inference results, confidence trends, and basic drift detection
for deployed models.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from collections import defaultdict
import json
import logging

from app.db.session import get_db_connection
from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.services.database import DatasetService

router = APIRouter()
logger = logging.getLogger(__name__)


class InferenceLog(BaseModel):
    dataset_id: str
    model_job_id: Optional[str] = None
    model_name: Optional[str] = None
    image_name: str
    detections: List[Dict[str, Any]]
    confidence_scores: List[float]
    num_detections: int
    inference_time_ms: Optional[float] = None


def _save_log(log: InferenceLog) -> bool:
    connection = get_db_connection()
    if not connection:
        return False
    try:
        class_counts: Dict[str, int] = {}
        for det in log.detections:
            cls_name = det.get("class", det.get("class_name", "unknown"))
            class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

        avg_confidence = (
            sum(log.confidence_scores) / len(log.confidence_scores)
            if log.confidence_scores else 0
        )

        cursor = connection.cursor()
        cursor.execute(
            """INSERT INTO monitoring_logs
               (dataset_id, model_job_id, model_name, image_name,
                num_detections, confidence_scores, avg_confidence,
                class_counts, inference_time_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                log.dataset_id,
                log.model_job_id,
                log.model_name,
                log.image_name,
                log.num_detections,
                json.dumps(log.confidence_scores),
                avg_confidence,
                json.dumps(class_counts),
                log.inference_time_ms,
            ),
        )
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save monitoring log: {e}")
        return False
    finally:
        connection.close()


def _load_logs(dataset_id: str, limit: int = 10000) -> List[Dict]:
    connection = get_db_connection()
    if not connection:
        return []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT model_job_id, model_name, image_name, num_detections,
                      confidence_scores, avg_confidence, class_counts,
                      inference_time_ms,
                      DATE_FORMAT(created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') AS timestamp
               FROM monitoring_logs
               WHERE dataset_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (dataset_id, limit),
        )
        rows = cursor.fetchall()
        cursor.close()
        # Parse JSON fields
        for row in rows:
            row["confidence_scores"] = json.loads(row["confidence_scores"] or "[]")
            row["class_counts"] = json.loads(row["class_counts"] or "{}")
        return list(reversed(rows))  # oldest-first for trend calcs
    except Exception as e:
        logger.error(f"Failed to load monitoring logs: {e}")
        return []
    finally:
        connection.close()


@router.post("/log")
async def log_inference(
    log: InferenceLog,
    current_user: dict = Depends(get_current_user),
):
    """Log an inference result for monitoring."""
    dataset = DatasetService.get_dataset(log.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(log.dataset_id, current_user["id"], dataset["user_id"], "annotator")
    _save_log(log)
    return {"success": True, "logged": True}


@router.get("/stats/{dataset_id}")
async def get_monitoring_stats(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get aggregated monitoring statistics for a dataset."""
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")
    logs = _load_logs(dataset_id)

    if not logs:
        return {
            "dataset_id": dataset_id,
            "total_inferences": 0,
            "avg_confidence": 0,
            "avg_detections_per_image": 0,
            "class_distribution": {},
            "confidence_trend": [],
            "recent_predictions": [],
        }

    total = len(logs)
    all_confidences: List[float] = []
    all_detections: List[int] = []
    class_dist: Dict[str, int] = defaultdict(int)

    for entry in logs:
        all_confidences.extend(entry.get("confidence_scores", []))
        all_detections.append(entry.get("num_detections", 0))
        for cls_name, count in entry.get("class_counts", {}).items():
            class_dist[cls_name] += count

    avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0
    avg_detections = sum(all_detections) / len(all_detections) if all_detections else 0

    batch_size = max(1, total // 20)
    confidence_trend = []
    for i in range(0, total, batch_size):
        batch = logs[i : i + batch_size]
        batch_confs: List[float] = []
        for entry in batch:
            batch_confs.extend(entry.get("confidence_scores", []))
        if batch_confs:
            confidence_trend.append({
                "batch_index": len(confidence_trend),
                "avg_confidence": round(sum(batch_confs) / len(batch_confs), 4),
                "num_inferences": len(batch),
                "timestamp": batch[-1].get("timestamp", ""),
            })

    return {
        "dataset_id": dataset_id,
        "total_inferences": total,
        "avg_confidence": round(avg_confidence, 4),
        "avg_detections_per_image": round(avg_detections, 2),
        "class_distribution": dict(class_dist),
        "confidence_trend": confidence_trend,
        "recent_predictions": logs[-10:][::-1],
    }


@router.get("/drift/{dataset_id}")
async def check_drift(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Basic drift detection: compare class distribution in recent vs older predictions."""
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")
    logs = _load_logs(dataset_id)

    if len(logs) < 20:
        return {
            "dataset_id": dataset_id,
            "drift_detected": False,
            "message": "Not enough data for drift detection (need at least 20 inferences)",
            "details": {},
        }

    mid = len(logs) // 2
    old_logs = logs[:mid]
    new_logs = logs[mid:]

    old_dist: Dict[str, int] = defaultdict(int)
    new_dist: Dict[str, int] = defaultdict(int)
    old_total = 0
    new_total = 0

    for entry in old_logs:
        for cls, count in entry.get("class_counts", {}).items():
            old_dist[cls] += count
            old_total += count

    for entry in new_logs:
        for cls, count in entry.get("class_counts", {}).items():
            new_dist[cls] += count
            new_total += count

    all_classes = set(list(old_dist.keys()) + list(new_dist.keys()))
    drift_details: Dict[str, Any] = {}
    max_shift = 0.0

    for cls in all_classes:
        old_pct = (old_dist.get(cls, 0) / old_total * 100) if old_total > 0 else 0
        new_pct = (new_dist.get(cls, 0) / new_total * 100) if new_total > 0 else 0
        shift = abs(new_pct - old_pct)
        max_shift = max(max_shift, shift)
        drift_details[cls] = {
            "old_percentage": round(old_pct, 2),
            "new_percentage": round(new_pct, 2),
            "shift": round(shift, 2),
            "direction": "increased" if new_pct > old_pct else "decreased",
        }

    old_confs: List[float] = []
    new_confs: List[float] = []
    for entry in old_logs:
        old_confs.extend(entry.get("confidence_scores", []))
    for entry in new_logs:
        new_confs.extend(entry.get("confidence_scores", []))

    old_avg_conf = sum(old_confs) / len(old_confs) if old_confs else 0
    new_avg_conf = sum(new_confs) / len(new_confs) if new_confs else 0
    conf_shift = new_avg_conf - old_avg_conf

    drift_detected = max_shift > 15 or conf_shift < -0.10

    return {
        "dataset_id": dataset_id,
        "drift_detected": drift_detected,
        "severity": (
            "high" if max_shift > 25 or conf_shift < -0.20
            else "medium" if drift_detected
            else "low"
        ),
        "confidence_shift": round(conf_shift, 4),
        "old_avg_confidence": round(old_avg_conf, 4),
        "new_avg_confidence": round(new_avg_conf, 4),
        "max_class_shift": round(max_shift, 2),
        "class_details": drift_details,
        "recommendation": (
            "Consider re-training your model with more recent data."
            if drift_detected
            else "Model performance appears stable."
        ),
    }


@router.delete("/clear/{dataset_id}")
async def clear_monitoring_data(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Clear all monitoring data for a dataset."""
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "admin")
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM monitoring_logs WHERE dataset_id = %s", (dataset_id,))
        connection.commit()
        cursor.close()
        return {"success": True, "message": "Monitoring data cleared"}
    except Exception as e:
        logger.error(f"Failed to clear monitoring logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()
