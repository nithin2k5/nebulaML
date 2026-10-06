"""
Publishing endpoints.

This module holds the only anonymous data path in the application, so it
carries two routers and the split between them is the security boundary:

    router         every handler takes `current_user` and checks a project role
    public_router  no authentication at all; the slug is the only credential

Nothing in `public_router` accepts an id, a path, or a format that is not
checked against an allowlist, and nothing it returns is assembled anywhere but
`publishing.public_payload`. Keep it that way: a handler added here without
`current_user` is world-readable by construction.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.db.session import db_cursor
from app.services import publishing
from app.services.database import DatasetService

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

_MAX_TITLE = 200
_MAX_DESCRIPTION = 4000
_MAX_LICENSE = 100


class PublishRequest(BaseModel):
    dataset_id: str
    version_id: str
    title: str = Field(..., min_length=1, max_length=_MAX_TITLE)
    description: str = Field("", max_length=_MAX_DESCRIPTION)
    license: str = Field("CC BY 4.0", max_length=_MAX_LICENSE)
    allow_downloads: bool = True
    formats: List[str] = Field(default_factory=lambda: list(publishing.PUBLIC_FORMATS))

    @validator("formats")
    def _known_formats(cls, value):
        unknown = [fmt for fmt in value if fmt not in publishing.PUBLIC_FORMATS]
        if unknown:
            raise ValueError(
                f"unsupported formats {unknown}; choose from {list(publishing.PUBLIC_FORMATS)}"
            )
        return value or list(publishing.PUBLIC_FORMATS)


class PublicationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=_MAX_TITLE)
    description: Optional[str] = Field(None, max_length=_MAX_DESCRIPTION)
    license: Optional[str] = Field(None, max_length=_MAX_LICENSE)
    allow_downloads: Optional[bool] = None


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------


def _fetch_by_id(publication_id: str) -> Optional[Dict[str, Any]]:
    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT * FROM dataset_publications WHERE id = %s", (publication_id,)
        )
        return cursor.fetchone()


def _fetch_live_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """A publication that is currently live, by its public slug.

    Revoked rows are filtered in the query rather than checked afterwards, so
    there is no path where a revoked publication is loaded and then forgotten
    about.
    """
    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT * FROM dataset_publications WHERE slug = %s AND status = 'live'",
            (slug,),
        )
        return cursor.fetchone()


def _owned_publication(publication_id: str, current_user: dict) -> Dict[str, Any]:
    """Load a publication the caller may administer."""
    publication = _fetch_by_id(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Publication not found")
    dataset = DatasetService.get_dataset(publication["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(
        publication["dataset_id"], current_user["id"], dataset["user_id"], "admin"
    )
    return publication


def _bump(slug: str, column: str) -> None:
    """Increment a counter without letting a failure break the response."""
    if column not in ("view_count", "download_count"):
        raise ValueError(f"refusing to increment {column}")
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE dataset_publications SET {column} = {column} + 1 "
                "WHERE slug = %s",
                (slug,),
            )
    except Exception as e:
        logger.warning(f"publishing: could not record {column} for {slug}: {e}")


# ---------------------------------------------------------------------------
# Management — authenticated, project admin
# ---------------------------------------------------------------------------


@router.post("")
async def publish_version(
    request: PublishRequest,
    current_user: dict = Depends(get_current_user),
):
    """Publish a frozen version behind a fresh public link."""
    dataset = DatasetService.get_dataset(request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Publishing exposes the project's data to the internet, so it is an
    # admin act — an annotator can label, not release.
    require_role(request.dataset_id, current_user["id"], dataset["user_id"], "admin")

    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT dataset_id FROM dataset_versions WHERE id = %s",
            (request.version_id,),
        )
        version = cursor.fetchone()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    if version["dataset_id"] != request.dataset_id:
        raise HTTPException(
            status_code=400, detail="That version belongs to a different project"
        )

    summary = publishing.summarise_version(request.version_id, dataset.get("classes") or [])
    if not summary["total_images"]:
        raise HTTPException(
            status_code=400,
            detail="This version's snapshot is empty, so there is nothing to publish.",
        )

    publication_id = str(uuid.uuid4())
    slug = publishing.new_slug()
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO dataset_publications "
                "(id, slug, dataset_id, version_id, title, description, license, "
                " allow_downloads, formats, published_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    publication_id, slug, request.dataset_id, request.version_id,
                    request.title, request.description, request.license,
                    request.allow_downloads, json.dumps(request.formats),
                    current_user["id"],
                ),
            )
    except Exception as e:
        logger.error(f"publishing: could not create publication: {e}")
        raise HTTPException(status_code=500, detail="Could not publish") from None

    logger.info(
        f"User {current_user['id']} published version {request.version_id} "
        f"of dataset {request.dataset_id}"
    )
    return {
        "id": publication_id,
        "slug": slug,
        "path": f"/d/{slug}",
        "status": "live",
        "total_images": summary["total_images"],
    }


@router.get("/dataset/{dataset_id}")
async def list_publications(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Every publication of a project, live and revoked, newest first."""
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "viewer")

    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT p.id, p.slug, p.version_id, p.title, p.description, p.license, "
            "       p.status, p.allow_downloads, p.formats, p.view_count, "
            "       p.download_count, p.published_at, p.revoked_at, "
            "       v.version_number "
            "FROM dataset_publications p "
            "LEFT JOIN dataset_versions v ON v.id = p.version_id "
            "WHERE p.dataset_id = %s ORDER BY p.published_at DESC",
            (dataset_id,),
        )
        rows = cursor.fetchall() or []

    for row in rows:
        if isinstance(row.get("formats"), (str, bytes)):
            try:
                row["formats"] = json.loads(row["formats"])
            except (ValueError, TypeError):
                row["formats"] = []
        row["path"] = f"/d/{row['slug']}"

    return {"dataset_id": dataset_id, "total": len(rows), "publications": rows}


@router.patch("/{publication_id}")
async def update_publication(
    publication_id: str,
    update: PublicationUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Edit a publication's card, or turn its downloads off."""
    publication = _owned_publication(publication_id, current_user)
    if publication["status"] != "live":
        raise HTTPException(
            status_code=409, detail="This publication has been revoked"
        )

    fields = {k: v for k, v in update.dict().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")

    assignments = ", ".join(f"{column} = %s" for column in fields)
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            f"UPDATE dataset_publications SET {assignments} WHERE id = %s",
            (*fields.values(), publication_id),
        )
    return {"id": publication_id, "updated": sorted(fields)}


@router.delete("/{publication_id}")
async def revoke_publication(
    publication_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Take a public link offline, permanently.

    The row is kept so the slug can never be reissued and the counts stay
    auditable, but the cached archives are deleted — leaving a built zip on
    disk after revocation is how "unpublished" data stays downloadable.
    """
    publication = _owned_publication(publication_id, current_user)

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE dataset_publications "
            "SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, "
            "    allow_downloads = FALSE "
            "WHERE id = %s",
            (publication_id,),
        )
    publishing.discard_archives(publication["slug"])
    logger.info(f"User {current_user['id']} revoked publication {publication_id}")
    return {"id": publication_id, "status": "revoked"}


# ---------------------------------------------------------------------------
# Public — NO AUTHENTICATION BELOW THIS LINE
#
# Every handler resolves everything from the slug. None of them takes a user,
# a dataset id, or a filesystem path. Rate limits are per client IP, because
# the slug is the only thing a caller presents and a leaked one should not be
# a free bandwidth tap.
# ---------------------------------------------------------------------------


@public_router.get("/datasets/{slug}")
@limiter.limit("60/minute")
async def public_dataset_card(slug: str, request: Request):
    """The dataset card: what it contains, and what can be downloaded."""
    publication = _fetch_live_by_slug(slug)
    if not publication:
        # The same answer whether the slug never existed or was revoked, so
        # probing cannot distinguish "wrong" from "withdrawn".
        raise HTTPException(status_code=404, detail="No such dataset")

    dataset = DatasetService.get_dataset(publication["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="No such dataset")

    _bump(slug, "view_count")
    return publishing.public_payload(publication, dataset)


@public_router.get("/datasets/{slug}/image/{index}")
@limiter.limit("240/minute")
async def public_preview_image(slug: str, index: int, request: Request):
    """One preview image, addressed by index within the published snapshot."""
    publication = _fetch_live_by_slug(slug)
    if not publication:
        raise HTTPException(status_code=404, detail="No such dataset")

    # Previews stop at the number the card advertises, so the endpoint is not
    # a way to walk the whole snapshot image by image.
    if index < 0 or index >= publishing.MAX_PREVIEWS:
        raise HTTPException(status_code=404, detail="No such preview")

    path = publishing.image_path_at(publication["version_id"], index)
    if path is None:
        raise HTTPException(status_code=404, detail="No such preview")

    return FileResponse(
        path=str(path),
        media_type="image/jpeg",
        headers={
            # Deliberately public: the content is published, and a shared cache
            # holding it is the point rather than a leak.
            "Cache-Control": "public, max-age=3600",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@public_router.get("/datasets/{slug}/download")
@limiter.limit("10/minute")
async def public_download(slug: str, request: Request, format: str = "yolo"):
    """Download the published snapshot in one of its offered formats."""
    publication = _fetch_live_by_slug(slug)
    if not publication:
        raise HTTPException(status_code=404, detail="No such dataset")
    if not publication.get("allow_downloads"):
        raise HTTPException(
            status_code=403, detail="Downloads are turned off for this dataset"
        )

    formats = publication.get("formats")
    if isinstance(formats, (str, bytes)):
        try:
            formats = json.loads(formats)
        except (ValueError, TypeError):
            formats = []
    # Checked against what this publication offers, not just the global
    # allowlist, so turning a format off actually turns it off.
    if format not in (formats or []):
        raise HTTPException(status_code=404, detail=f"Format not offered: {format}")

    dataset = DatasetService.get_dataset(publication["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="No such dataset")

    archive = publishing.build_archive(
        slug,
        publication["version_id"],
        dataset.get("classes") or [],
        publication["title"],
        format,
    )
    if archive is None:
        raise HTTPException(status_code=404, detail="That download is unavailable")

    _bump(slug, "download_count")
    suffix = "json" if format == "coco" else "zip"
    return FileResponse(
        path=str(archive),
        # Named from the slug, never the project's or the uploader's filenames.
        filename=f"{slug}_{format}.{suffix}",
        media_type="application/json" if format == "coco" else "application/zip",
        headers={"X-Content-Type-Options": "nosniff"},
    )
