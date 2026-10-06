"""
In-app assistant endpoint.

The reply shape is unchanged — `{"role": "assistant", "content": ...}` — so the
existing widget and tab keep working. What is new is `dataset_id`: when the
caller is inside a project and the user can read it, the project's own numbers
go into the system prompt, which is what lets the answer be about this dataset
rather than about object detection in general.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.v1.endpoints.auth import get_current_user
from app.core.access import effective_role
from app.services import assistant
from app.services.assistant import AssistantUnavailable
from app.services.database import DatasetService

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 8000


def _with_note(answer: str, note: str) -> str:
    """Mark a fallback answer as one, so it is not mistaken for a grounded one."""
    return f"{answer}\n\n({note})"


@router.post("")
async def chat_with_assistant(
    messages: List[Dict[str, str]] = Body(..., embed=True),
    dataset_id: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(get_current_user),
):
    """Answer a question, grounded in the project's data when one is named."""
    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")

    last_message = (messages[-1].get("content") or "")[:MAX_MESSAGE_CHARS]

    # Project context is only assembled for a project the caller can actually
    # read. Without this check the assistant would be a way to read any
    # project's class list and metrics by guessing its id.
    project_context = ""
    if dataset_id:
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset and effective_role(dataset_id, current_user["id"], dataset["user_id"]):
            try:
                project_context = assistant.build_project_context(dataset_id)
            except Exception as e:  # noqa: BLE001 - answer without it rather than 500
                logger.warning("Could not build project context for %s: %s", dataset_id, e)
        else:
            logger.info(
                "Assistant context skipped: user %s cannot read dataset %s",
                current_user["id"], dataset_id,
            )

    if not assistant.is_configured():
        return {
            "role": "assistant",
            "content": _with_note(
                assistant.rule_based_reply(last_message),
                "No assistant model is configured on this server, so this is a canned "
                "answer rather than one based on your project's data. Set "
                "ANTHROPIC_API_KEY to enable the full assistant.",
            ),
            "grounded": False,
        }

    try:
        content = assistant.answer(messages, project_context)
    except AssistantUnavailable as e:
        # A configured-but-unreachable model is an operator problem, not the
        # user's: say what happened and still answer what can be answered,
        # rather than failing the request.
        logger.warning("Assistant unavailable: %s", e)
        return {
            "role": "assistant",
            "content": _with_note(
                assistant.rule_based_reply(last_message),
                f"The assistant model is configured but could not answer: {e}. "
                "This is a canned answer instead.",
            ),
            "grounded": False,
        }

    return {
        "role": "assistant",
        "content": content,
        # Lets the UI distinguish "answered from your project's data" from a
        # fallback, instead of both looking equally authoritative.
        "grounded": bool(project_context),
    }
