"""
Publishing a frozen dataset version behind a public link.

Everything else in this application is reached with a bearer token or an API
key. A publication is the one exception, so the rules it plays by are written
down here rather than spread across the route handlers:

* **A version, never the live dataset.** A public link has to keep meaning the
  same thing. The live dataset changes every time somebody draws a box, and the
  version snapshot on disk is already a complete dataset.
* **The slug is the whole credential.** It is a random token, long enough not to
  be guessed, and it is the only thing an anonymous caller presents. Internal
  ids are deliberately not reachable from it.
* **Nothing about people goes out.** The public payload is built by naming the
  fields that may leave, not by removing the ones that may not — so a column
  added to the table later is private by default instead of published by
  accident.
* **Images are addressed by index.** Snapshot filenames embed the original
  image's uuid and, before that, whatever the uploader called the file. An
  index leaks neither, and an integer needs no path sanitising.
"""

import json
import secrets
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.db.session import db_cursor

# Where version snapshots live, mirroring DatasetVersionManager.
VERSIONS_DIR = Path("uploads/versions")

# Built archives are cached here. A public link can be fetched repeatedly by
# anyone, so rebuilding a multi-gigabyte zip per request would be a denial of
# service with extra steps.
PUBLICATIONS_DIR = Path("uploads/publications")

# Formats a publication can offer. An allowlist, because the format name
# reaches a filename.
PUBLIC_FORMATS: Tuple[str, ...] = ("yolo", "coco")

# Slug entropy: 24 bytes of urlsafe base64. The slug is the only thing standing
# between the internet and the data, so it is sized to be unguessable rather
# than pretty.
_SLUG_BYTES = 24

# How many preview images a dataset card offers.
MAX_PREVIEWS = 12


def new_slug() -> str:
    """A fresh, unguessable public identifier."""
    return secrets.token_urlsafe(_SLUG_BYTES)


# ── Reading a snapshot ───────────────────────────────────────────────────────


def _snapshot_rows(version_id: str) -> List[Dict[str, Any]]:
    """Every image row of a version, ordered so an index is stable."""
    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT filename, path, split, width, height, boxes "
                "FROM dataset_version_images WHERE version_id = %s "
                "ORDER BY filename",
                (version_id,),
            )
            rows = cursor.fetchall() or []
    except Exception as e:
        logger.error(f"publishing: could not read snapshot {version_id}: {e}")
        return []

    for row in rows:
        boxes = row.get("boxes")
        if isinstance(boxes, (str, bytes)):
            try:
                row["boxes"] = json.loads(boxes)
            except (ValueError, TypeError):
                row["boxes"] = []
        row["boxes"] = row.get("boxes") or []
    return rows


def summarise_version(version_id: str, classes: List[str]) -> Dict[str, Any]:
    """
    Counts for the dataset card: images per split, boxes per class.

    Derived from the snapshot rows rather than the live dataset's stats, so the
    numbers describe what a downloader actually receives.
    """
    rows = _snapshot_rows(version_id)
    splits: Dict[str, int] = {}
    per_class = dict.fromkeys(classes, 0)
    total_boxes = 0

    for row in rows:
        split = row.get("split") or "train"
        splits[split] = splits.get(split, 0) + 1
        for box in row["boxes"]:
            total_boxes += 1
            class_id = box.get("class_id", 0)
            if isinstance(class_id, int) and 0 <= class_id < len(classes):
                per_class[classes[class_id]] += 1

    return {
        "total_images": len(rows),
        "total_boxes": total_boxes,
        "splits": splits,
        "classes": [
            {"name": name, "boxes": per_class[name]} for name in classes
        ],
        "preview_count": min(len(rows), MAX_PREVIEWS),
    }


def image_path_at(version_id: str, index: int) -> Optional[Path]:
    """
    The file behind a preview index, or None.

    The stored path is confirmed to sit inside the versions tree before it is
    handed back. The rows are ours, but this is the one place an anonymous
    request turns into a file read, so it does not get to trust the database.
    """
    rows = _snapshot_rows(version_id)
    if index < 0 or index >= len(rows):
        return None

    raw = rows[index].get("path")
    if not raw:
        return None

    try:
        path = Path(raw).resolve()
        root = VERSIONS_DIR.resolve()
    except OSError as e:
        logger.error(f"publishing: could not resolve {raw}: {e}")
        return None

    if root not in path.parents:
        logger.error(f"publishing: refusing {path} — outside {root}")
        return None
    if not path.is_file():
        return None
    return path


# ── Building archives ────────────────────────────────────────────────────────


def _cache_dir(slug: str) -> Path:
    directory = PUBLICATIONS_DIR / slug
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def coco_from_snapshot(version_id: str, classes: List[str], title: str) -> Dict[str, Any]:
    """
    Build COCO JSON from a snapshot.

    Snapshot boxes are YOLO's normalised centre form; COCO wants absolute
    [x, y, width, height] from the top-left, so each box is converted against
    its own image's dimensions rather than a dataset-wide size — a version's
    images are not all the same shape once preprocessing has run.
    """
    rows = _snapshot_rows(version_id)
    images: List[Dict[str, Any]] = []
    annotations: List[Dict[str, Any]] = []
    annotation_id = 1

    for image_id, row in enumerate(rows, start=1):
        width = int(row.get("width") or 0)
        height = int(row.get("height") or 0)
        images.append({
            "id": image_id,
            "file_name": row["filename"],
            "width": width,
            "height": height,
        })
        if width <= 0 or height <= 0:
            continue

        for box in row["boxes"]:
            norm = box.get("bbox_normalized")
            if not norm or len(norm) < 4:
                continue
            try:
                cx, cy, bw, bh = (float(v) for v in norm[:4])
            except (TypeError, ValueError):
                continue
            box_width = bw * width
            box_height = bh * height
            if box_width <= 0 or box_height <= 0:
                continue
            annotations.append({
                "id": annotation_id,
                "image_id": image_id,
                # COCO category ids are 1-based.
                "category_id": int(box.get("class_id", 0)) + 1,
                "bbox": [
                    (cx - bw / 2.0) * width,
                    (cy - bh / 2.0) * height,
                    box_width,
                    box_height,
                ],
                "area": box_width * box_height,
                "iscrowd": 0,
            })
            annotation_id += 1

    return {
        "info": {"description": title},
        "images": images,
        "annotations": annotations,
        "categories": [
            {"id": index + 1, "name": name, "supercategory": "none"}
            for index, name in enumerate(classes)
        ],
    }


def build_archive(
    slug: str, version_id: str, classes: List[str], title: str, fmt: str
) -> Optional[Path]:
    """
    The downloadable file for one format, built once and cached.

    Returns None when the format is unknown or the snapshot is missing, so the
    caller answers 404 rather than surfacing a path.
    """
    if fmt not in PUBLIC_FORMATS:
        return None

    version_dir = VERSIONS_DIR / version_id
    if not version_dir.is_dir():
        logger.error(f"publishing: snapshot directory missing for {version_id}")
        return None

    cache = _cache_dir(slug)

    if fmt == "coco":
        target = cache / f"{slug}_coco.json"
        if not target.exists():
            payload = coco_from_snapshot(version_id, classes, title)
            target.write_text(json.dumps(payload, indent=2))
        return target

    # yolo: the snapshot is already a YOLO dataset on disk — images, label
    # files and data.yaml — so publishing it is a zip rather than a conversion,
    # which means the published form is exactly what training consumed.
    target = cache / f"{slug}_yolo.zip"
    if target.exists():
        return target

    partial = target.with_suffix(".zip.partial")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(version_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(version_dir))
        # Published under its final name only once complete, so a download that
        # arrives mid-build does not get a truncated zip from the cache.
        partial.replace(target)
    except OSError as e:
        logger.error(f"publishing: could not build {fmt} archive for {slug}: {e}")
        partial.unlink(missing_ok=True)
        return None
    return target


def discard_archives(slug: str) -> None:
    """Delete a publication's cached archives. Called when it is revoked."""
    directory = PUBLICATIONS_DIR / slug
    if not directory.is_dir():
        return
    try:
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()
        directory.rmdir()
    except OSError as e:
        logger.warning(f"publishing: could not clear archives for {slug}: {e}")


# ── The public payload ───────────────────────────────────────────────────────


def public_payload(
    publication: Dict[str, Any], dataset: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Everything an anonymous caller is allowed to see, and nothing else.

    Built by naming what may leave rather than by stripping what may not. A
    column added to `dataset_publications` later is therefore private until
    somebody adds it here on purpose — the opposite default to returning the
    row and deleting a few keys, which publishes every future column by
    accident.

    Specifically absent: the dataset and version ids, the publisher, every
    member of the project, file paths, and the project's own name unless it was
    chosen as the title.
    """
    classes = dataset.get("classes") or []
    formats = publication.get("formats")
    if isinstance(formats, (str, bytes)):
        try:
            formats = json.loads(formats)
        except (ValueError, TypeError):
            formats = []

    offered = [fmt for fmt in (formats or []) if fmt in PUBLIC_FORMATS]
    published_at = publication.get("published_at")

    return {
        "slug": publication["slug"],
        "title": publication["title"],
        "description": publication.get("description") or "",
        "license": publication.get("license") or "",
        "published_at": published_at.isoformat() if published_at else None,
        "downloads_enabled": bool(publication.get("allow_downloads")),
        "formats": offered if publication.get("allow_downloads") else [],
        "summary": summarise_version(publication["version_id"], classes),
    }
