"""
Label audit: run a trained model over labelled data to find bad labels.

The review queue this produces is the point. A reviewer opens it, works
top-down (most damaging kind, most confident model first), and marks each
finding fixed or dismissed — a dismissal sticks, so re-running the audit after
more training does not resurface the same judged box.

See `app.services.label_audit` for the method and its honest caveat about
scoring data the model trained on.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.db.session import db_cursor
from app.services import error_analysis as ea
from app.services import label_audit
from app.services.database import AnnotationService, DatasetService

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[4]
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

audit_jobs: Dict[str, Dict[str, Any]] = {}

_TERMINAL_STATUSES = {"completed", "failed"}
_FINISHED_JOB_RETENTION = 20

DEFAULT_MAX_IMAGES = 500


def _prune_finished_jobs(jobs: Dict[str, Dict], keep: int = _FINISHED_JOB_RETENTION) -> None:
    """Drop all but the most recent `keep` finished jobs, oldest first."""
    finished = [
        job_id for job_id, job in jobs.items()
        if job.get("status") in _TERMINAL_STATUSES
    ]
    for job_id in finished[:-keep] if keep else finished:
        jobs.pop(job_id, None)


class AuditRequest(BaseModel):
    dataset_id: str
    job_id: str = Field(..., description="Training job whose model does the auditing.")
    min_confidence: float = Field(
        label_audit.DEFAULT_CONFIDENCE, ge=0.5, le=0.99,
        description="How sure the model must be before it may flag a label.",
    )
    max_images: int = Field(DEFAULT_MAX_IMAGES, ge=1, le=5000)


class ResolveRequest(BaseModel):
    finding_ids: List[str] = Field(..., min_length=1, max_length=500)
    status: str = Field(..., pattern="^(fixed|dismissed|open)$")


def _owned_dataset(dataset_id: str, user_id: int, minimum: str = "viewer") -> Dict:
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, user_id, dataset["user_id"], minimum)
    return dataset


def _resolve_weights(job_id: str) -> Optional[Path]:
    """Locate a job's weights, with the same containment check as elsewhere."""
    weights_dir = (_RUNS_BASE / f"job_{job_id}" / "weights").resolve()
    if not str(weights_dir).startswith(str(_RUNS_BASE)):
        return None
    for name in ("best.pt", "best.onnx", "last.pt"):
        candidate = weights_dir / name
        if candidate.exists():
            return candidate
    return None


def _dismissed_keys(dataset_id: str) -> set:
    """
    (image_id, kind, labelled_class, predicted_class) a reviewer already judged.

    Keyed on the finding's substance rather than its row id, because a re-run
    generates new ids for the same underlying complaint. Without this, every
    audit would re-raise everything the reviewer dismissed last time.
    """
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT image_id, kind, labelled_class, predicted_class "
                "FROM label_audit_findings "
                "WHERE dataset_id = %s AND status IN ('dismissed', 'fixed')",
                (dataset_id,),
            )
            return {tuple(row) for row in cursor.fetchall() or []}
    except Exception as e:
        logger.error(f"Could not read judged findings for {dataset_id}: {e}")
        return set()


def _scan_images(
    model: Any,
    dataset_id: str,
    images: List[Dict],
    annotations: Dict[str, List[Dict]],
    class_names: Dict[int, str],
    min_confidence: float,
    judged: set,
    progress: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Tuple], int]:
    """
    Audit each image's labels. Returns (rows_to_insert, images_scanned).

    An unreadable image is skipped rather than failing the run.
    """
    rows: List[Tuple] = []
    scanned = 0

    for index, image in enumerate(images):
        path = Path(image.get("path") or "")
        if not path.is_absolute():
            path = Path("datasets") / dataset_id / "images" / image["filename"]
        if not path.exists():
            continue

        try:
            # A low floor so `spurious_label` can see weak detections; the
            # confidence gate for accusing a label is applied in audit_image.
            detections = model.predict(str(path), conf_threshold=0.01)
        except Exception as e:
            logger.warning(f"Label audit: inference failed on {path}: {e}")
            continue

        scanned += 1
        findings = label_audit.audit_image(
            ea.detections_to_arrays(detections),
            ea.gt_boxes_to_xyxy(annotations.get(image["id"], [])),
            class_names=class_names,
            min_confidence=min_confidence,
        )

        for finding in findings:
            key = (
                image["id"],
                finding["kind"],
                finding.get("labelled_class"),
                finding.get("predicted_class"),
            )
            if key in judged:
                continue
            rows.append((
                str(uuid.uuid4()),
                dataset_id,
                image["id"],
                image.get("filename"),
                finding["kind"],
                label_audit.severity_of(finding["kind"]),
                finding.get("confidence"),
                finding.get("labelled_class"),
                finding.get("predicted_class"),
                json.dumps(finding),
            ))

        if progress is not None:
            progress["progress"] = index + 1

    return rows, scanned


def _audit_task(audit_id: str, request: AuditRequest) -> None:
    """Run the audit and replace this dataset's open findings."""
    progress = audit_jobs.get(audit_id)

    def mark(status: str, **extra: Any) -> None:
        if progress is not None:
            progress["status"] = status
            progress.update(extra)

    mark("running")
    try:
        from app.services.inference import YOLOInference

        weights = _resolve_weights(request.job_id)
        if weights is None:
            raise RuntimeError("No trained weights found for that job")

        dataset = DatasetService.get_dataset(request.dataset_id)
        if not dataset:
            raise RuntimeError("Dataset not found")

        # Only annotated images have labels to audit.
        images = [img for img in dataset.get("images") or [] if img.get("annotated")]
        images = images[: request.max_images]
        if not images:
            raise RuntimeError("This dataset has no annotated images to audit")

        annotations = {
            row["image_id"]: row.get("boxes") or []
            for row in AnnotationService.get_all_dataset_annotations(request.dataset_id)
        }

        if progress is not None:
            progress["total"] = len(images)

        rows, scanned = _scan_images(
            model=YOLOInference(str(weights)),
            dataset_id=request.dataset_id,
            images=images,
            annotations=annotations,
            class_names=dict(enumerate(dataset.get("classes") or [])),
            min_confidence=request.min_confidence,
            judged=_dismissed_keys(request.dataset_id),
            progress=progress,
        )

        # Replace the open queue; judged findings are left alone, which is what
        # makes a dismissal durable across re-runs.
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM label_audit_findings "
                "WHERE dataset_id = %s AND status = 'open'",
                (request.dataset_id,),
            )
            if rows:
                cursor.executemany(
                    "INSERT INTO label_audit_findings "
                    "(id, dataset_id, image_id, filename, kind, severity, "
                    " confidence, labelled_class, predicted_class, detail) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )

        mark("completed", findings=len(rows), images_scanned=scanned)
        logger.info(
            f"Label audit on {request.dataset_id}: {len(rows)} finding(s) "
            f"across {scanned} image(s)"
        )
    except Exception as e:
        logger.error(f"Label audit {audit_id} failed: {e}")
        mark("failed", error=str(e))


@router.post("/run")
async def run_audit(
    request: AuditRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Audit a dataset's labels using one of its trained models."""
    _owned_dataset(request.dataset_id, current_user["id"], "annotator")

    if _resolve_weights(request.job_id) is None:
        raise HTTPException(
            status_code=409,
            detail="No trained weights for that job yet.",
        )

    audit_id = str(uuid.uuid4())
    _prune_finished_jobs(audit_jobs)
    audit_jobs[audit_id] = {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "dataset_id": request.dataset_id,
    }

    background_tasks.add_task(_audit_task, audit_id, request)

    return {
        "success": True,
        "audit_id": audit_id,
        "message": "Auditing labels in the background",
    }


@router.get("/status/{audit_id}")
async def audit_status(audit_id: str, current_user: dict = Depends(get_current_user)):
    """Poll a running audit."""
    job = audit_jobs.get(audit_id)
    if not job:
        raise HTTPException(status_code=404, detail="Audit job not found")
    _owned_dataset(job["dataset_id"], current_user["id"])
    return job


@router.get("/findings/{dataset_id}")
async def list_findings(
    dataset_id: str,
    kind: Optional[str] = None,
    status: str = "open",
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """
    The review queue, most damaging and most confident first.

    That ordering is the feature: a reviewer works down it and stops when the
    findings stop being worth the time.
    """
    _owned_dataset(dataset_id, current_user["id"])

    if status not in ("open", "fixed", "dismissed", "all"):
        raise HTTPException(
            status_code=400,
            detail="status must be open, fixed, dismissed or all",
        )
    if kind and kind not in label_audit.FINDING_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {', '.join(label_audit.FINDING_KINDS)}",
        )

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    where = ["dataset_id = %s"]
    params: List[Any] = [dataset_id]
    if status != "all":
        where.append("status = %s")
        params.append(status)
    if kind:
        where.append("kind = %s")
        params.append(kind)
    clause = " AND ".join(where)

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id, image_id, filename, kind, severity, confidence, "
                "       labelled_class, predicted_class, detail, status "
                f"FROM label_audit_findings WHERE {clause} "
                # NULL confidence (spurious_label) sorts last within a severity
                # band rather than first, which MySQL would otherwise do.
                "ORDER BY severity DESC, confidence IS NULL, confidence DESC "
                "LIMIT %s OFFSET %s",
                (*params, limit, offset),
            )
            rows = cursor.fetchall() or []

            cursor.execute(
                f"SELECT COUNT(*) AS total FROM label_audit_findings WHERE {clause}",
                params,
            )
            total = (cursor.fetchone() or {}).get("total", 0)
    except Exception as e:
        logger.error(f"Could not list findings for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not list findings") from None

    for row in rows:
        detail = row.get("detail")
        if isinstance(detail, (str, bytes, bytearray)):
            try:
                row["detail"] = json.loads(detail)
            except (ValueError, TypeError):
                row["detail"] = None

    return {
        "dataset_id": dataset_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "findings": rows,
    }


@router.get("/summary/{dataset_id}")
async def findings_summary(
    dataset_id: str, current_user: dict = Depends(get_current_user)
):
    """Counts by kind and the label pairs most often confused."""
    _owned_dataset(dataset_id, current_user["id"])

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT kind, labelled_class, predicted_class "
                "FROM label_audit_findings "
                "WHERE dataset_id = %s AND status = 'open'",
                (dataset_id,),
            )
            rows = cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Could not summarise findings for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load summary") from None

    summary = label_audit.summarise(rows)
    summary["dataset_id"] = dataset_id
    summary["kind_meanings"] = {
        "wrong_class": "the box is right, the label is not",
        "missing_label": "an object nobody drew a box around",
        "spurious_label": "a box with nothing in it",
        "loose_box": "the right class, but the extent is off",
    }
    summary["caveat"] = (
        "The auditing model was trained on these labels, so it tends to agree "
        "with them. That costs findings rather than inventing them: the flags "
        "are worth reviewing, but a clean report is not proof the labels are "
        "clean."
    )
    return summary


@router.post("/resolve/{dataset_id}")
async def resolve_findings(
    dataset_id: str,
    request: ResolveRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Mark findings fixed or dismissed.

    A judged finding is excluded from later audits, so dismissing a false flag
    only has to be done once.
    """
    _owned_dataset(dataset_id, current_user["id"], "annotator")

    placeholders = ",".join(["%s"] * len(request.finding_ids))
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE label_audit_findings SET status = %s "
                f"WHERE dataset_id = %s AND id IN ({placeholders})",
                (request.status, dataset_id, *request.finding_ids),
            )
            updated = cursor.rowcount
    except Exception as e:
        logger.error(f"Could not resolve findings for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not update findings") from None

    return {"success": True, "updated": updated, "status": request.status}
