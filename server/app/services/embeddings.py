"""
Image and text embeddings for semantic search, similarity and coverage analysis.

One CLIP model sits behind four features: text search over a dataset, "find
images like this one", embedding-space duplicate detection, and diversity
sampling for active learning. They all reduce to the same two primitives —
encode something into a unit vector, then take dot products against a matrix
of stored vectors.

Design notes:

* The model is loaded lazily and only once. Importing this module must stay
  free, because it is imported by endpoint modules that FastAPI loads at
  startup; pulling ~600MB of CLIP weights there would make the API unbootable
  on a machine that has never run a search.
* `transformers` and `torch` are already hard dependencies (the trainers need
  them), but the *weights* are a runtime download. Everything here degrades to
  "feature unavailable" rather than raising, so a offline deployment keeps the
  rest of the platform working.
* Vectors are stored L2-normalised, which makes cosine similarity a plain dot
  product and lets a whole dataset be scored with one matrix multiply. At the
  scale this platform targets (thousands of images per dataset, not millions)
  exact search in numpy is faster than building an ANN index, and it cannot
  return the subtly wrong neighbours an approximate index can.
"""

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# numpy and torch are hard requirements of the trainers, but guarding them
# keeps this module importable on a slim install so the rest of the API boots.
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# The smallest CLIP that still separates scenes usefully. 512-dim output keeps
# a 10k-image dataset at ~20MB of vectors, which loads fast and fits in memory.
DEFAULT_MODEL = "openai/clip-vit-base-patch32"
EMBEDDING_DIM = 512

# float32 little-endian is what numpy's tobytes() produces on every platform we
# support. Stored in the DB as a BLOB; the column records the dim so a model
# swap can be detected rather than silently reinterpreted.
VECTOR_DTYPE = "float32"

_model = None
_processor = None
_model_name: Optional[str] = None
_load_failed = False
_load_lock = threading.Lock()


def is_available() -> bool:
    """True when embeddings can be computed (or already have been loaded)."""
    return HAS_NUMPY and HAS_TORCH and not _load_failed


def _load_model(model_name: str = DEFAULT_MODEL) -> Tuple[Any, Any]:
    """
    Load CLIP once, under a lock.

    Returns (model, processor), or (None, None) when the weights cannot be
    obtained. The failure is sticky: a deployment with no network should not
    pay a multi-second timeout on every search request.
    """
    global _model, _processor, _model_name, _load_failed

    if _load_failed:
        return None, None
    if _model is not None and _model_name == model_name:
        return _model, _processor

    with _load_lock:
        # Re-check inside the lock; another request may have just loaded it.
        if _model is not None and _model_name == model_name:
            return _model, _processor
        if _load_failed:
            return None, None

        if not (HAS_NUMPY and HAS_TORCH):
            logger.warning("Embeddings unavailable: numpy/torch not importable")
            _load_failed = True
            return None, None

        try:
            from transformers import CLIPModel, CLIPProcessor

            logger.info(f"Loading embedding model {model_name} (first use)")
            model = CLIPModel.from_pretrained(model_name)
            model.eval()
            processor = CLIPProcessor.from_pretrained(model_name)

            _model, _processor, _model_name = model, processor, model_name
            logger.info("✓ Embedding model ready")
            return _model, _processor
        except Exception as e:
            # Most likely no network on first use, or a transformers version
            # that moved CLIPProcessor. Either way: stay up, report unavailable.
            logger.error(f"Could not load embedding model {model_name}: {e}")
            _load_failed = True
            return None, None


def reset_model_cache() -> None:
    """Drop the loaded model. Exists for tests and for retrying after a failure."""
    global _model, _processor, _model_name, _load_failed
    with _load_lock:
        _model = None
        _processor = None
        _model_name = None
        _load_failed = False


def _normalise(matrix: "np.ndarray") -> "np.ndarray":
    """
    L2-normalise rows, leaving all-zero rows alone.

    A zero row would otherwise divide by zero and poison every later dot
    product with NaN, which is how a single unreadable image could break
    search for a whole dataset.
    """
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(VECTOR_DTYPE)


def embed_images(
    paths: Sequence[Path],
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 16,
) -> Tuple[List[Path], Optional["np.ndarray"]]:
    """
    Encode images into unit vectors.

    Returns (paths_that_worked, matrix). Unreadable images are dropped from
    both, so row *i* of the matrix always belongs to `paths_that_worked[i]` —
    callers never have to reconcile two lists of different length.
    """
    model, processor = _load_model(model_name)
    if model is None:
        return [], None

    ok_paths: List[Path] = []
    chunks: List["np.ndarray"] = []

    for start in range(0, len(paths), batch_size):
        batch_paths = list(paths[start:start + batch_size])
        images = []
        batch_ok = []
        for path in batch_paths:
            try:
                with Image.open(path) as im:
                    # CLIP's processor wants RGB; palette and grayscale images
                    # would otherwise arrive with the wrong channel count.
                    images.append(im.convert("RGB").copy())
                batch_ok.append(path)
            except Exception as e:
                logger.warning(f"Skipping unreadable image {path}: {e}")

        if not images:
            continue

        try:
            with torch.no_grad():
                inputs = processor(images=images, return_tensors="pt")
                features = model.get_image_features(**inputs)
            chunks.append(features.cpu().numpy().astype(VECTOR_DTYPE))
            ok_paths.extend(batch_ok)
        except Exception as e:
            # A bad batch should cost us that batch, not the whole index job.
            logger.error(f"Embedding batch at offset {start} failed: {e}")
        finally:
            for im in images:
                try:
                    im.close()
                except Exception:
                    pass

    if not chunks:
        return [], None

    return ok_paths, _normalise(np.vstack(chunks))


def embed_text(
    queries: Sequence[str],
    model_name: str = DEFAULT_MODEL,
) -> Optional["np.ndarray"]:
    """Encode text prompts into unit vectors in the same space as the images."""
    model, processor = _load_model(model_name)
    if model is None or not queries:
        return None

    try:
        with torch.no_grad():
            inputs = processor(
                text=list(queries),
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            features = model.get_text_features(**inputs)
        return _normalise(features.cpu().numpy().astype(VECTOR_DTYPE))
    except Exception as e:
        logger.error(f"Text embedding failed: {e}")
        return None


def vector_to_blob(vector: "np.ndarray") -> bytes:
    """Serialise one vector for storage."""
    return np.asarray(vector, dtype=VECTOR_DTYPE).tobytes()


def blob_to_vector(blob: bytes) -> Optional["np.ndarray"]:
    """
    Deserialise one stored vector.

    Returns None for a truncated blob rather than letting numpy raise, so one
    corrupt row cannot take down a whole dataset load.
    """
    if not HAS_NUMPY or not blob:
        return None
    try:
        vector = np.frombuffer(blob, dtype=VECTOR_DTYPE)
        return vector if vector.size else None
    except Exception as e:
        logger.warning(f"Discarding corrupt embedding blob: {e}")
        return None


def stack_vectors(
    rows: Iterable[Tuple[str, bytes]],
) -> Tuple[List[str], Optional["np.ndarray"]]:
    """
    Turn (image_id, blob) rows into an id list and an aligned matrix.

    Rows whose vector is unreadable, or whose width disagrees with the majority,
    are dropped: mixing dims would make the matrix multiply fail outright, and a
    stale vector from a previous model is worse than a missing one.
    """
    if not HAS_NUMPY:
        return [], None

    decoded: List[Tuple[str, "np.ndarray"]] = []
    for image_id, blob in rows:
        vector = blob_to_vector(blob)
        if vector is not None:
            decoded.append((image_id, vector))

    if not decoded:
        return [], None

    # Majority dim wins, so a handful of leftovers from an older model get
    # discarded instead of dictating the shape.
    dims: Dict[int, int] = {}
    for _, vector in decoded:
        dims[vector.size] = dims.get(vector.size, 0) + 1
    target_dim = max(dims.items(), key=lambda kv: kv[1])[0]

    kept = [(i, v) for i, v in decoded if v.size == target_dim]
    dropped = len(decoded) - len(kept)
    if dropped:
        logger.warning(
            f"Ignored {dropped} embedding(s) with unexpected dim "
            f"(kept dim={target_dim})"
        )

    ids = [image_id for image_id, _ in kept]
    matrix = np.vstack([v for _, v in kept]).astype(VECTOR_DTYPE)
    return ids, matrix


def rank_by_similarity(
    query: "np.ndarray",
    matrix: "np.ndarray",
    ids: Sequence[str],
    limit: int = 50,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Score every row against one query vector and return the best matches.

    Both sides are unit vectors, so the dot product *is* cosine similarity.
    """
    if matrix is None or not len(ids):
        return []

    scores = matrix @ np.asarray(query, dtype=VECTOR_DTYPE).reshape(-1)

    # argpartition finds the top-k without sorting the whole array, which
    # matters once a dataset has tens of thousands of images.
    limit = max(1, min(limit, len(ids)))
    top = np.argpartition(-scores, limit - 1)[:limit]
    top = top[np.argsort(-scores[top])]

    return [
        {"image_id": ids[i], "score": round(float(scores[i]), 4)}
        for i in top
        if float(scores[i]) >= min_score
    ]


def find_near_duplicates(
    matrix: "np.ndarray",
    ids: Sequence[str],
    threshold: float = 0.95,
    max_pairs: int = 500,
) -> List[Dict[str, Any]]:
    """
    Pairs whose cosine similarity exceeds `threshold`.

    This catches what perceptual hashing cannot: the same scene at a different
    exposure, crop or compression level, which pHash sees as unrelated because
    its bits are driven by pixel layout rather than content.

    The full similarity matrix is computed blockwise so peak memory stays at
    `block x n` floats rather than `n x n` — at 20k images the latter would be
    1.6GB.
    """
    if matrix is None or len(ids) < 2:
        return []

    pairs: List[Dict[str, Any]] = []
    n = len(ids)
    block = 512

    for start in range(0, n, block):
        stop = min(start + block, n)
        sims = matrix[start:stop] @ matrix.T

        for local_row, global_row in enumerate(range(start, stop)):
            row = sims[local_row]
            # Only look forward, so each pair is reported once and an image is
            # never compared with itself.
            candidates = np.nonzero(row[global_row + 1:] >= threshold)[0]
            for offset in candidates:
                col = global_row + 1 + int(offset)
                pairs.append({
                    "image_a": ids[global_row],
                    "image_b": ids[col],
                    "similarity": round(float(row[col]), 4),
                })
                if len(pairs) >= max_pairs:
                    pairs.sort(key=lambda p: -p["similarity"])
                    return pairs

    pairs.sort(key=lambda p: -p["similarity"])
    return pairs


def kmeans(
    matrix: "np.ndarray",
    k: int,
    iterations: int = 25,
    seed: int = 0,
) -> Tuple["np.ndarray", "np.ndarray"]:
    """
    Minimal k-means++ over unit vectors.

    Returns (labels, centroids). Written out rather than pulled from sklearn,
    which is not a dependency of this project and would be a heavy addition for
    one routine. On unit vectors, Euclidean distance and cosine distance rank
    neighbours identically, so plain squared distance is the right objective.
    """
    n = len(matrix)
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)

    # k-means++ seeding: first centre at random, each later centre drawn with
    # probability proportional to its squared distance from the nearest centre.
    # Random seeding on embedding data reliably produces empty clusters.
    centroids = np.empty((k, matrix.shape[1]), dtype=VECTOR_DTYPE)
    centroids[0] = matrix[rng.integers(n)]
    closest = np.sum((matrix - centroids[0]) ** 2, axis=1)
    for i in range(1, k):
        total = float(closest.sum())
        if total <= 0:
            # Every point already coincides with a centre; the rest are
            # arbitrary and duplicates here are harmless.
            centroids[i] = matrix[rng.integers(n)]
        else:
            centroids[i] = matrix[rng.choice(n, p=closest / total)]
        closest = np.minimum(
            closest, np.sum((matrix - centroids[i]) ** 2, axis=1)
        )

    labels = np.zeros(n, dtype=int)
    for _ in range(iterations):
        # (n, k) distances via the dot-product identity, avoiding an (n, k, d)
        # temporary that would dominate memory on a real dataset.
        dists = (
            np.sum(matrix ** 2, axis=1, keepdims=True)
            - 2 * (matrix @ centroids.T)
            + np.sum(centroids ** 2, axis=1)
        )
        new_labels = np.argmin(dists, axis=1)
        if _ and np.array_equal(new_labels, labels):
            break
        labels = new_labels

        for i in range(k):
            members = matrix[labels == i]
            if len(members):
                centroids[i] = members.mean(axis=0)
            # An empty cluster keeps its old centroid rather than becoming NaN.

    return labels, centroids


def diverse_sample(
    matrix: "np.ndarray",
    ids: Sequence[str],
    count: int,
    priority: Optional[Sequence[float]] = None,
) -> List[str]:
    """
    Pick `count` ids that are spread out in embedding space.

    This is the fix for uncertainty-only active learning, which happily returns
    forty near-identical frames of one hard scene — all genuinely low
    confidence, all teaching the model the same thing. Clustering first and
    then taking the best candidate per cluster buys coverage for the same
    review budget.

    `priority` (higher = better, e.g. 1 - confidence) decides the winner within
    each cluster; without it the member nearest the centroid is used, which is
    the most representative image of that group.
    """
    if matrix is None or not len(ids):
        return []

    count = max(1, min(count, len(ids)))
    if count == len(ids):
        return list(ids)

    labels, centroids = kmeans(matrix, count)

    picks: List[str] = []
    for cluster in range(len(centroids)):
        members = np.nonzero(labels == cluster)[0]
        if not len(members):
            continue
        if priority is not None:
            scores = np.asarray(priority, dtype="float64")[members]
            winner = members[int(np.argmax(scores))]
        else:
            dists = np.sum((matrix[members] - centroids[cluster]) ** 2, axis=1)
            winner = members[int(np.argmin(dists))]
        picks.append(ids[int(winner)])

    # Empty clusters can leave us short of `count`; top up with whatever ranks
    # highest by priority among the ids not already chosen.
    if len(picks) < count:
        chosen = set(picks)
        remaining = [i for i in range(len(ids)) if ids[i] not in chosen]
        if priority is not None:
            remaining.sort(key=lambda i: -float(priority[i]))
        for i in remaining[: count - len(picks)]:
            picks.append(ids[i])

    return picks


def nearest_member(
    matrix: "np.ndarray",
    member_idx: Sequence[int],
    centroid: "np.ndarray",
) -> Optional[int]:
    """
    Index (into `matrix`) of the cluster member closest to `centroid`.

    The most representative image of a group, which is what a cluster should
    show as its thumbnail. Lives here so callers do not need numpy imported.
    """
    if matrix is None or not len(member_idx):
        return None
    rows = np.asarray(list(member_idx), dtype=int)
    dists = np.sum((matrix[rows] - centroid) ** 2, axis=1)
    return int(rows[int(np.argmin(dists))])
