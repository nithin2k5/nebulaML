"""
Webhook subscription management.

Admin-only throughout: a hook receives the project's event payloads, and the
server will POST to whatever URL is registered, so adding one is a privileged
act rather than an annotator-level convenience.
"""

import logging
import secrets
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import require_role
from app.services import webhooks as webhook_service
from app.services.database import DatasetService
from app.services.webhooks import WebhookValidationError

router = APIRouter()
logger = logging.getLogger(__name__)


class WebhookCreate(BaseModel):
    dataset_id: str
    url: str
    events: List[str]


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None


def _require_admin(dataset_id: str, current_user: dict) -> dict:
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_role(dataset_id, current_user["id"], dataset["user_id"], "admin")
    return dataset


def _owned_webhook(webhook_id: str, current_user: dict) -> dict:
    """Load a hook and assert admin on the project it belongs to."""
    hook = webhook_service.get_webhook(webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    _require_admin(hook["dataset_id"], current_user)
    return hook


@router.get("/events")
async def list_event_types(current_user: dict = Depends(get_current_user)):
    """The events a hook can subscribe to, for populating the UI."""
    return {"events": list(webhook_service.EVENTS)}


@router.get("/{dataset_id}")
async def list_project_webhooks(
    dataset_id: str, current_user: dict = Depends(get_current_user)
):
    """Every hook on a project, with the outcome of its last delivery."""
    _require_admin(dataset_id, current_user)
    return {
        "webhooks": webhook_service.list_webhooks(dataset_id),
        "events": list(webhook_service.EVENTS),
        "max_consecutive_failures": webhook_service.MAX_CONSECUTIVE_FAILURES,
    }


@router.post("")
async def create_webhook(
    body: WebhookCreate, current_user: dict = Depends(get_current_user)
):
    """Register a hook and return its signing secret.

    The secret is shown exactly once, here: deliveries need the original key to
    sign with, so it is stored as-is and never returned by a read path. If it
    is lost, delete the hook and make a new one.
    """
    _require_admin(body.dataset_id, current_user)

    try:
        url = webhook_service.validate_url(body.url)
        events = webhook_service.validate_events(body.events)
    except WebhookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    webhook_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    webhook_service.create_webhook(webhook_id, body.dataset_id, url, secret, events)

    return {
        "success": True,
        "id": webhook_id,
        "secret": secret,
        "signature_header": webhook_service.SIGNATURE_HEADER,
        "message": "Save this secret now — it is not shown again.",
    }


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: str, body: WebhookUpdate, current_user: dict = Depends(get_current_user)
):
    """Change a hook's URL, subscriptions, or enabled state."""
    _owned_webhook(webhook_id, current_user)

    url = None
    events = None
    try:
        if body.url is not None:
            url = webhook_service.validate_url(body.url)
        if body.events is not None:
            events = webhook_service.validate_events(body.events)
    except WebhookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if url is None and events is None and body.enabled is None:
        raise HTTPException(status_code=400, detail="Nothing to update")

    webhook_service.update_webhook(webhook_id, url, events, body.enabled)
    return {"success": True}


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, current_user: dict = Depends(get_current_user)):
    """Remove a hook. Its secret goes with it."""
    _owned_webhook(webhook_id, current_user)
    webhook_service.delete_webhook(webhook_id)
    return {"success": True}


@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str, current_user: dict = Depends(get_current_user)):
    """Send a signed test delivery and report what the receiver said.

    Synchronous on purpose, unlike real events: the person configuring a hook
    is waiting to find out whether their endpoint and signature check work,
    and that answer is the entire point of the request.
    """
    hook = _owned_webhook(webhook_id, current_user)
    delivery_id = str(uuid.uuid4())
    ok = webhook_service.deliver(
        hook,
        "training.completed",
        {
            "test": True,
            "note": "Test delivery from NebulaML. Shaped like a real training.completed event.",
            "job_id": "00000000-0000-0000-0000-000000000000",
            "model_name": "yolov8s.pt",
            "metrics": {"map50": 0.0, "map50-95": 0.0, "precision": 0.0, "recall": 0.0},
        },
        delivery_id,
    )

    refreshed = [
        w for w in webhook_service.list_webhooks(hook["dataset_id"]) if w["id"] == webhook_id
    ]
    return {
        "success": ok,
        "delivery_id": delivery_id,
        "webhook": refreshed[0] if refreshed else None,
    }
