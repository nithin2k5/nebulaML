"""
In-app assistant.

Replaces a rule-based mock that matched substrings ("train" in the message ->
paste the training paragraph) and could therefore only ever restate the
documentation. This version calls Claude with tools that read the asking user's
own projects, so it can answer questions about *their* data: how much labelling
is left, what the last run scored, which classes the model confuses, which
images match a description.

Design notes:

* **Manual tool loop, not the SDK's beta tool runner.** Every tool needs the
  calling user threaded through it for authorisation, and the runner's
  decorator form wants module-level functions — per-request closures to carry
  the user would be worse than the loop. It also keeps the chat path off a beta
  API surface.
* **Read-only tools.** The assistant has no confirmation UI, so it does not get
  to start runs or delete anything. See `assistant_tools` for the reasoning.
* **Degrades instead of failing.** With no ANTHROPIC_API_KEY configured — a
  normal state for a self-hosted install that does not want outbound calls —
  the endpoint answers with a short rule-based reply and says the assistant is
  not configured, rather than returning a 500.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.v1.endpoints.auth import get_current_user
from app.core.config import settings
from app.services.assistant_tools import TOOL_DEFINITIONS, run_tool

router = APIRouter()
logger = logging.getLogger(__name__)

# Long enough for a useful answer, short enough that one question cannot run
# away with the bill.
MAX_TOKENS = 4096

# The conversation window sent upstream. Each turn resends the history, so an
# unbounded window would grow cost without bound on a long session.
MAX_HISTORY_MESSAGES = 20

MAX_MESSAGE_CHARS = 8000

SYSTEM_PROMPT = """You are Nebula AI, the assistant built into NebulaML — a \
self-hosted platform for the object-detection lifecycle: upload, annotate, \
version, train, evaluate, deploy and monitor.

You have read-only tools over the user's own projects. Prefer calling them over \
guessing: if the user asks about their data, their labels, or how a run did, \
look it up. When a user names a project in words, call list_projects first to \
resolve the id.

The platform's workflow, as tabs on a project, is: Upload, Images, Annotate, \
Health, Version (freeze a snapshot), Train, Evaluate, Registry, Test, Deploy, \
Active Learning, Monitoring, Team. Training always runs against a frozen \
version rather than the live dataset, which is what makes a run reproducible.

How to answer:

- Be concrete and brief. Cite the numbers you looked up.
- When the user asks why a model is underperforming, call get_evaluation and \
reason from the error breakdown. The failure kinds imply different fixes: many \
wrong_class errors between two labels means those classes need disambiguating \
examples; poor_localisation means box regression is weak; duplicate usually \
means NMS is too permissive; background suggests more hard negatives; missed \
on a rare class usually means more examples of it.
- Say plainly when something has not been computed yet, and name the tab that \
would produce it.
- Never invent metrics, counts or filenames. If a tool returns an error or an \
empty result, say so.
- You cannot change anything — no starting runs, no editing labels, no \
deleting. Explain where in the UI the user can do it instead."""


# The old rule-based replies, kept as the unconfigured fallback. They are a
# worse answer than the model gives, but better than an error.
_FALLBACK_RULES = (
    (("train", "model"), (
        "To train a model, open a project and go to the Train tab. You pick a "
        "backend and a frozen dataset version, run preflight, and start the "
        "job; progress, metrics and per-class results stream live."
    )),
    (("dataset", "upload"), (
        "Create a project from the dashboard, then use its Upload tab to add "
        "images — drag them in, import a ZIP, or extract frames from a video."
    )),
    (("annotate", "label"), (
        "The Annotate tab draws bounding boxes by hand, auto-labels from an "
        "existing model so you only correct the results, and can propagate "
        "boxes across images."
    )),
    (("evaluate", "wrong", "bad"), (
        "The Evaluate tab scores a finished run against a held-out split and "
        "breaks its mistakes down by kind — hallucinated boxes, wrong class, "
        "loose boxes, duplicates and misses — with a per-image list."
    )),
    (("deploy", "api"), (
        "The Deploy tab exports the weights (pt, onnx, engine, coreml) or "
        "gives you an API key to call the model over HTTP."
    )),
)

_FALLBACK_DEFAULT = (
    "I can answer questions about your projects — labelling progress, dataset "
    "health, how a training run scored and where it goes wrong — but this "
    "server has no ANTHROPIC_API_KEY configured, so I am limited to canned "
    "answers right now. Set that key to enable the full assistant."
)


def _fallback_reply(message: str) -> str:
    """The unconfigured answer: match a topic, else say what is missing."""
    lowered = message.lower()
    for keywords, reply in _FALLBACK_RULES:
        if any(keyword in lowered for keyword in keywords):
            return f"{reply}\n\n(The full assistant needs ANTHROPIC_API_KEY set on the server.)"
    return _FALLBACK_DEFAULT


def _sanitise(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Normalise client history into Messages API turns.

    Anything that is not a non-empty user/assistant text turn is dropped: the
    client is the only source of this list, and a malformed role would be
    rejected upstream with an error the user cannot act on. A leading assistant
    turn is also dropped, because the first message must be from the user.
    """
    cleaned: List[Dict[str, Any]] = []
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if not cleaned and role != "user":
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})

    # Consecutive same-role turns are legal, so no merging is needed.
    return cleaned


def _answer_with_tools(history: List[Dict[str, Any]], user: Dict) -> Dict[str, Any]:
    """
    Run the tool-use loop until Claude stops asking for tools.

    Returns the reply text plus which tools ran, so the UI can show its work.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    messages: List[Dict[str, Any]] = list(history)
    tools_used: List[str] = []

    for _ in range(max(1, settings.assistant_max_tool_rounds)):
        response = client.messages.create(
            model=settings.assistant_model,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # A safety decline arrives as a 200 with no usable content, so it has
        # to be checked before reading blocks.
        if response.stop_reason == "refusal":
            return {
                "content": (
                    "I can't answer that one. Try rephrasing, or ask me about "
                    "your projects, labels or training runs."
                ),
                "tools_used": tools_used,
            }

        tool_calls = [block for block in response.content if block.type == "tool_use"]

        if not tool_calls:
            text = "\n\n".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            return {
                "content": text or "I could not put together an answer for that.",
                "tools_used": tools_used,
            }

        # Echo the assistant turn back verbatim — including thinking blocks,
        # which must survive unchanged for the model to continue its reasoning.
        messages.append({"role": "assistant", "content": response.content})

        # All results for one assistant turn go back in a single user message;
        # splitting them teaches the model to stop calling tools in parallel.
        results = []
        for call in tool_calls:
            tools_used.append(call.name)
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": run_tool(call.name, dict(call.input or {}), user),
            })
        messages.append({"role": "user", "content": results})

    # Out of rounds. Saying so is better than presenting a half-finished
    # investigation as a complete answer.
    return {
        "content": (
            "I looked at several things but could not settle on an answer "
            "within my step limit. Try narrowing the question to one project."
        ),
        "tools_used": tools_used,
    }


@router.post("")
async def chat_with_assistant(
    messages: List[Dict[str, str]] = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
):
    """
    Answer a question about the caller's projects.

    Takes the conversation so far (`messages`: role/content turns) and returns
    one assistant turn. Tools run server-side between the request and the
    reply, each re-checking that this user may read what it touches.
    """
    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")

    history = _sanitise(messages)
    if not history:
        raise HTTPException(
            status_code=400, detail="No usable user message in the conversation"
        )

    last_user = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), ""
    )

    if not settings.anthropic_api_key:
        return {
            "role": "assistant",
            "content": _fallback_reply(last_user),
            "configured": False,
            "tools_used": [],
        }

    try:
        answer = _answer_with_tools(history, current_user)
    except ImportError:
        logger.error("assistant: the anthropic package is not installed")
        return {
            "role": "assistant",
            "content": (
                "The assistant needs the `anthropic` package, which is not "
                "installed on this server. Run `pip install -r requirements.txt`."
            ),
            "configured": False,
            "tools_used": [],
        }
    except Exception as e:
        # Narrow the common, actionable failures; everything else is a 502,
        # since the failure is upstream rather than in the request.
        import anthropic

        if isinstance(e, anthropic.AuthenticationError):
            logger.error("assistant: ANTHROPIC_API_KEY was rejected")
            raise HTTPException(
                status_code=502,
                detail="The configured Anthropic API key was rejected.",
            ) from None
        if isinstance(e, anthropic.RateLimitError):
            raise HTTPException(
                status_code=429,
                detail="The assistant is rate limited right now. Try again shortly.",
            ) from None
        if isinstance(e, anthropic.APIConnectionError):
            raise HTTPException(
                status_code=502,
                detail="Could not reach the Anthropic API from this server.",
            ) from None

        logger.error(f"assistant failed: {e}")
        raise HTTPException(
            status_code=502, detail="The assistant could not answer that."
        ) from None

    return {
        "role": "assistant",
        "content": answer["content"],
        "configured": True,
        "tools_used": answer["tools_used"],
    }
