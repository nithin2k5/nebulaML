"""
Semantic search, visual similarity and embedding-space dataset analysis.

Everything here reads from `image_embeddings`, which is populated by the index
job below. Indexing is explicit rather than automatic on upload: encoding a few
thousand images takes minutes on CPU, and making every upload wait on it would
be the wrong trade for a feature not every project uses.
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.db.session import db_cursor
from app.services import embeddings
from app.services.database import DatasetService

router = APIRouter()
logger = logging.getLogger(__name__)

# Indexing progress, same in-memory pattern the export and auto-label jobs use.
index_jobs: Dict[str, Dict[str, Any]] = {}

_TERMINAL_STATUSES = {"completed", "failed"}
_FINISHED_JOB_RETENTION = 20


def _prune_finished_jobs(jobs: Dict[str, Dict], keep: int = _FINISHED_JOB_RETENTION) -> None:
    """Drop all but the most recent `keep` finished jobs, oldest first."""
    finished = [
        job_id for job_id, job in jobs.items()
        if job.get("status") in _TERMINAL_STATUSES
    ]
    for job_id in finished[:-keep] if keep else finished:
        jobs.pop(job_id, None)


class TextSearchRequest(BaseModel):
    dataset_id: str
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(50, ge=1, le=500)
    # CLIP similarities are compressed into a narrow band — in practice a
    # strong match sits near 0.30 and noise near 0.15 — so a 0-1 style cutoff
    # would filter out everything. Default to no cutoff and let the scores speak.
    min_score: float = Field(0.0, ge=-1.0, le=1.0)


class SimilarSearchRequest(BaseModel):
    dataset_id: str
    image_id: str
    limit: int = Field(25, ge=1, le=500)


def _require_dataset(dataset_id: str, user_id: int, minimum: str = "viewer") -> Dict:
    """Fetch a dataset and assert the caller holds at least `minimum` on it."""
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, user_id, dataset["user_id"], minimum)
    return dataset


def _load_dataset_vectors(dataset_id: str, model: str = embeddings.DEFAULT_MODEL):
    """Read every stored vector for a dataset as (ids, matrix)."""
    rows: List[Any] = []
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT image_id, vector FROM image_embeddings "
                "WHERE dataset_id = %s AND model = %s",
                (dataset_id, model),
            )
            rows = cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Could not load embeddings for {dataset_id}: {e}")
        return [], None

    return embeddings.stack_vectors((row[0], row[1]) for row in rows)


def _image_lookup(dataset: Dict) -> Dict[str, Dict]:
    """image_id -> image row, for decorating search hits with filenames."""
    return {img["id"]: img for img in dataset.get("images", [])}


def _decorate(hits: List[Dict], lookup: Dict[str, Dict]) -> List[Dict]:
    """
    Attach filenames to raw (image_id, score) hits.

    Hits whose image has since been deleted are dropped: the embedding row
    outlives the image only in the window before the cascade lands, and
    returning an id the client cannot render is worse than returning fewer.
    """
    decorated = []
    for hit in hits:
        image = lookup.get(hit["image_id"])
        if not image:
            continue
        decorated.append({
            **hit,
            "filename": image.get("filename"),
            "original_name": image.get("original_name"),
            "annotated": bool(image.get("annotated")),
            "split": image.get("split"),
        })
    return decorated


def _resolve_image_paths(
    dataset_id: str, images: List[Dict]
) -> Tuple[List[Path], Dict[str, str]]:
    """
    Map image rows to on-disk paths, skipping anything missing.

    Returns (paths, path -> image_id). A row whose `path` is relative is
    resolved against the dataset's upload directory, which is where the upload
    endpoint writes. Missing files are dropped here so the encode loop never
    has to handle them mid-batch.
    """
    resolved: List[Path] = []
    by_path: Dict[str, str] = {}
    for image in images:
        path = Path(image.get("path") or "")
        if not path.is_absolute():
            path = Path("datasets") / dataset_id / "images" / image["filename"]
        if path.exists():
            resolved.append(path)
            by_path[str(path)] = image["id"]
        else:
            logger.warning(f"Index: missing file for image {image['id']}")
    return resolved, by_path


def _index_task(job_id: str, dataset_id: str, images: List[Dict], model: str) -> None:
    """Encode every given image and upsert its vector. Runs in the background."""
    job = index_jobs.get(job_id)
    if job is None:
        return

    job["status"] = "running"
    try:
        resolved, by_path = _resolve_image_paths(dataset_id, images)

        if not resolved:
            job["status"] = "failed"
            job["error"] = "No readable images found for this dataset"
            return

        # Encode in chunks so progress moves and one bad batch is contained.
        chunk = 32
        written = 0
        for start in range(0, len(resolved), chunk):
            batch = resolved[start:start + chunk]
            ok_paths, matrix = embeddings.embed_images(batch, model_name=model)

            if matrix is None:
                if not embeddings.is_available():
                    job["status"] = "failed"
                    job["error"] = (
                        "Embedding model unavailable. The weights download on "
                        "first use and need network access."
                    )
                    return
                # Just a bad batch — keep going.
                job["progress"] = min(len(resolved), start + len(batch))
                continue

            payload = [
                (
                    by_path[str(path)],
                    dataset_id,
                    model,
                    int(matrix.shape[1]),
                    embeddings.vector_to_blob(matrix[i]),
                )
                for i, path in enumerate(ok_paths)
            ]
            try:
                with db_cursor(commit=True) as cursor:
                    cursor.executemany(
                        "INSERT INTO image_embeddings "
                        "(image_id, dataset_id, model, dim, vector) "
                        "VALUES (%s, %s, %s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE "
                        "  model = VALUES(model), dim = VALUES(dim), "
                        "  vector = VALUES(vector), created_at = CURRENT_TIMESTAMP",
                        payload,
                    )
                written += len(payload)
            except Exception as e:
                logger.error(f"Index: could not store batch at {start}: {e}")

            job["progress"] = min(len(resolved), start + len(batch))

        job["indexed"] = written
        job["status"] = "completed"
        logger.info(f"Indexed {written} embeddings for dataset {dataset_id}")
    except Exception as e:
        logger.error(f"Index job {job_id} failed: {e}")
        job["status"] = "failed"
        job["error"] = str(e)


@router.post("/index/{dataset_id}")
async def build_index(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """
    Compute embeddings for a dataset's images.

    By default only images with no vector yet are encoded, so this is cheap to
    re-run after an upload. `force=true` re-encodes everything, which is what
    you want after changing models.
    """
    dataset = _require_dataset(dataset_id, current_user["id"], "annotator")

    if not embeddings.is_available():
        raise HTTPException(
            status_code=503,
            detail="Embeddings unavailable: numpy and torch are required.",
        )

    images = dataset.get("images", [])
    if not images:
        raise HTTPException(status_code=400, detail="Dataset has no images")

    if not force:
        indexed_ids, _ = _load_dataset_vectors(dataset_id)
        already = set(indexed_ids)
        images = [img for img in images if img["id"] not in already]
        if not images:
            return {
                "success": True,
                "job_id": None,
                "message": "Every image is already indexed",
                "total": 0,
            }

    job_id = str(uuid.uuid4())
    _prune_finished_jobs(index_jobs)
    index_jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "total": len(images),
        "dataset_id": dataset_id,
    }

    background_tasks.add_task(
        _index_task, job_id, dataset_id, images, embeddings.DEFAULT_MODEL
    )

    return {
        "success": True,
        "job_id": job_id,
        "total": len(images),
        "message": f"Indexing {len(images)} image(s) in the background",
    }


@router.get("/index-status/{job_id}")
async def index_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """Poll an index job."""
    job = index_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Index job not found")
    return job


@router.get("/status/{dataset_id}")
async def index_coverage(dataset_id: str, current_user: dict = Depends(get_current_user)):
    """How much of a dataset is indexed — drives the "build index" prompt in the UI."""
    dataset = _require_dataset(dataset_id, current_user["id"])
    total = len(dataset.get("images", []))
    indexed_ids, _ = _load_dataset_vectors(dataset_id)

    return {
        "dataset_id": dataset_id,
        "total_images": total,
        "indexed_images": len(indexed_ids),
        "coverage": round(len(indexed_ids) / total, 4) if total else 0.0,
        "model": embeddings.DEFAULT_MODEL,
        "available": embeddings.is_available(),
    }


@router.post("/text")
async def search_by_text(
    request: TextSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Rank a dataset's images against a text prompt.

    Scores are cosine similarities in CLIP space, so they are comparable within
    one result set but not across different queries — "0.31" means "the best
    match for this phrasing", not "31% confident".
    """
    dataset = _require_dataset(request.dataset_id, current_user["id"])

    ids, matrix = _load_dataset_vectors(request.dataset_id)
    if matrix is None:
        raise HTTPException(
            status_code=409,
            detail="This dataset has no embeddings yet. Build the index first.",
        )

    query = embeddings.embed_text([request.query])
    if query is None:
        raise HTTPException(
            status_code=503, detail="Embedding model unavailable for text encoding."
        )

    hits = embeddings.rank_by_similarity(
        query[0], matrix, ids, limit=request.limit, min_score=request.min_score
    )

    return {
        "query": request.query,
        "count": len(hits),
        "results": _decorate(hits, _image_lookup(dataset)),
    }


@router.post("/similar")
async def search_similar(
    request: SimilarSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Find the images most like a given one."""
    dataset = _require_dataset(request.dataset_id, current_user["id"])

    ids, matrix = _load_dataset_vectors(request.dataset_id)
    if matrix is None:
        raise HTTPException(
            status_code=409,
            detail="This dataset has no embeddings yet. Build the index first.",
        )

    try:
        anchor = ids.index(request.image_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="That image is not indexed. Re-run the index to include it.",
        ) from None

    # Ask for one extra and drop the anchor, which always scores 1.0 against
    # itself and would otherwise eat a result slot.
    hits = embeddings.rank_by_similarity(
        matrix[anchor], matrix, ids, limit=request.limit + 1
    )
    hits = [h for h in hits if h["image_id"] != request.image_id][: request.limit]

    return {
        "image_id": request.image_id,
        "count": len(hits),
        "results": _decorate(hits, _image_lookup(dataset)),
    }


@router.get("/duplicates/{dataset_id}")
async def embedding_duplicates(
    dataset_id: str,
    threshold: float = 0.95,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """
    Near-duplicate pairs by embedding similarity.

    Complements the perceptual-hash pass in Health rather than replacing it:
    pHash is exact about pixel layout and catches re-saves, while this catches
    the same subject shot twice, which pHash scores as unrelated.
    """
    dataset = _require_dataset(dataset_id, current_user["id"])

    if not 0.0 < threshold <= 1.0:
        raise HTTPException(status_code=400, detail="threshold must be in (0, 1]")

    ids, matrix = _load_dataset_vectors(dataset_id)
    if matrix is None:
        raise HTTPException(
            status_code=409,
            detail="This dataset has no embeddings yet. Build the index first.",
        )

    pairs = embeddings.find_near_duplicates(
        matrix, ids, threshold=threshold, max_pairs=max(1, min(limit, 2000))
    )

    lookup = _image_lookup(dataset)
    enriched = []
    for pair in pairs:
        a, b = lookup.get(pair["image_a"]), lookup.get(pair["image_b"])
        if not a or not b:
            continue
        enriched.append({
            **pair,
            "filename_a": a.get("filename"),
            "filename_b": b.get("filename"),
        })

    return {
        "dataset_id": dataset_id,
        "threshold": threshold,
        "count": len(enriched),
        "pairs": enriched,
    }


@router.get("/clusters/{dataset_id}")
async def embedding_clusters(
    dataset_id: str,
    clusters: int = 8,
    current_user: dict = Depends(get_current_user),
):
    """
    Group a dataset into visual clusters and report annotation coverage per
    cluster.

    This is what turns "class balance" into something actionable: a cluster of
    900 images that is 2% annotated is a coverage gap you can go and fix, and
    it is invisible to a per-class histogram.
    """
    dataset = _require_dataset(dataset_id, current_user["id"])

    if not 2 <= clusters <= 50:
        raise HTTPException(status_code=400, detail="clusters must be between 2 and 50")

    ids, matrix = _load_dataset_vectors(dataset_id)
    if matrix is None:
        raise HTTPException(
            status_code=409,
            detail="This dataset has no embeddings yet. Build the index first.",
        )
    if len(ids) < clusters:
        raise HTTPException(
            status_code=400,
            detail=f"Only {len(ids)} indexed image(s); need at least {clusters}.",
        )

    labels, centroids = embeddings.kmeans(matrix, clusters)
    lookup = _image_lookup(dataset)

    groups: List[Dict[str, Any]] = []
    for cluster in range(len(centroids)):
        member_idx = [i for i, label in enumerate(labels) if int(label) == cluster]
        if not member_idx:
            continue

        members = [lookup.get(ids[i]) for i in member_idx]
        members = [m for m in members if m]
        annotated = sum(1 for m in members if m.get("annotated"))

        # The image closest to the centroid is the one that best represents the
        # cluster, which makes it the right thumbnail for the UI.
        anchor = embeddings.nearest_member(matrix, member_idx, centroids[cluster])
        representative = lookup.get(ids[anchor]) if anchor is not None else None

        groups.append({
            "cluster": cluster,
            "size": len(members),
            "annotated": annotated,
            "annotated_ratio": round(annotated / len(members), 4) if members else 0.0,
            "representative": {
                "image_id": representative.get("id") if representative else None,
                "filename": representative.get("filename") if representative else None,
            },
            "sample_image_ids": [m["id"] for m in members[:12]],
        })

    groups.sort(key=lambda g: -g["size"])

    # A big cluster that nobody has labelled is the headline finding, so call
    # it out explicitly rather than making the UI re-derive it.
    gaps = [
        {
            "cluster": g["cluster"],
            "size": g["size"],
            "annotated_ratio": g["annotated_ratio"],
            "message": (
                f"{g['size']} visually similar images, only "
                f"{int(g['annotated_ratio'] * 100)}% annotated"
            ),
        }
        for g in groups
        if g["size"] >= 5 and g["annotated_ratio"] < 0.25
    ]

    return {
        "dataset_id": dataset_id,
        "indexed_images": len(ids),
        "clusters": groups,
        "coverage_gaps": gaps,
    }
