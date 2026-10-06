"""
The in-app assistant.

This used to be a chain of `if "train" in last_message` branches returning four
hardcoded paragraphs, one of which advised checking a "Monitor tab" for logs
and another a "Help & Contact" tab that does not exist. It could not read
anything about the project it was embedded in, so the one class of question it
was in a position to answer better than the documentation — "why is *my* mAP
low", about *this* dataset — was the one it could not touch.

What makes answering that possible is that the platform already computes the
evidence: class balance and duplicate counts in the health snapshot, per-class
metrics on the finished run, the error mix from the evaluation workbench. The
job here is to put that evidence in front of the model as facts, so an answer
can cite the project's own numbers instead of restating general advice.

A deployment with no API key configured keeps working: the questions the old
rule-based replies covered are still answered that way, and the reply says so
rather than implying the model was consulted.
"""

import json
import logging
import os
from typing import Dict, List, Optional

from app.core.config import settings
from app.db.session import db_cursor
from app.services.database import (
    AnnotationService,
    DatasetService,
    DatasetVersionService,
    QualitySnapshotService,
)

logger = logging.getLogger(__name__)

# Chat answers are deliberately short, and the widget shows one reply at a
# time, so a 128K ceiling would only buy the chance to run long. Non-streaming
# keeps the existing single-JSON response contract the widget already reads.
MAX_TOKENS = 4096

# Only the last few turns are sent. The widget is for short exchanges, and the
# project context block is re-derived each turn anyway, so older turns add
# tokens without adding much.
MAX_HISTORY_TURNS = 12

SYSTEM_PROMPT = """You are the assistant built into NebulaML, a self-hosted \
platform for the object-detection lifecycle: upload, annotate, version, train, \
evaluate, deploy, monitor.

How the platform is actually laid out, so you never invent a tab:
- A project's tabs are Overview, Upload, Images, Annotate, Health, Generate \
("Version"), Train, Evaluate, Registry, Test, Deploy, Monitor, Active \
Learning, Classes, Team, Webhooks.
- Training never runs against the live dataset. It runs against a frozen \
version created in Generate, which is what makes a run reproducible.
- A version is frozen for one task: detection (box labels) or segmentation \
(polygon labels). A model must match its version's task.
- Evaluate classifies each wrong prediction as hallucinated, wrong-class, \
loose-box, duplicate or missed, because the fix differs for each.
- mAP is measured across the whole precision-recall curve, so it does not move \
with the confidence threshold. Precision, recall and the error mix do.

How to answer:
- Name the tab for each next step, and keep answers to a few sentences unless \
asked to go deeper. No preamble.
- Never invent a metric, a count, a tab or a feature. When you do not have a \
number, say which tab would produce it."""

# Appended only when the project's facts were actually assembled. The grounding
# instruction has to arrive with the data: telling the model to "quote the
# project context" when no context block follows invites it to invent one.
GROUNDING_PROMPT = """
PROJECT CONTEXT — the current state of the project the user is asking from. \
These are facts read from the database just now; prefer them over anything you \
assume.

{context}

Ground every claim about this project in the facts above and quote their \
numbers. Diagnose in terms of the specific numbers you can see: "your rarest \
class has 11 instances against 1,400 for the most common" is useful, "class \
imbalance can hurt accuracy" is not. If the facts above do not contain \
something you would need, say which tab would produce it rather than guessing \
a value."""

# Appended instead when there is no project in scope, so the model does not
# answer as though it could see one.
NO_CONTEXT_PROMPT = """
You have no data about any specific project in this conversation — the user is \
not viewing one, or you may not read it. Answer about how the platform works, \
and when a question turns on their own numbers, say which tab shows them \
instead of speculating about what those numbers are."""


def is_configured() -> bool:
    """Whether a credential for the Anthropic API is available.

    Only the environment is consulted, which is how a server deployment is
    configured. An `ant auth login` profile on the machine would also work for
    the SDK but is not detected here, so such a deployment falls back rather
    than failing.
    """
    return bool(
        settings.anthropic_api_key
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
    )


# ---------------------------------------------------------------------------
# Project context
# ---------------------------------------------------------------------------


def _latest_run(dataset_id: str) -> Optional[Dict]:
    """The most recent finished run for a project, with its metrics."""
    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT model_name, status, epochs, results, error_message, created_at
                FROM training_jobs
                WHERE dataset_id = %s AND status IN ('completed', 'failed')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (dataset_id,),
            )
            row = cursor.fetchone()
    except Exception as e:  # noqa: BLE001 - context is best-effort
        logger.warning("Could not read latest run for %s: %s", dataset_id, e)
        return None

    if not row:
        return None
    if isinstance(row.get("results"), (str, bytes)):
        try:
            row["results"] = json.loads(row["results"])
        except (ValueError, TypeError):
            row["results"] = {}
    return row


def _class_balance(stats: Dict, limit: int = 12) -> Optional[str]:
    """The rarest and most common classes, which is what imbalance looks like.

    The whole distribution is not sent — on a 60-class project that is most of
    the budget — but the ends of it are what a question about imbalance is
    actually about.
    """
    counts = stats.get("class_distribution") or stats.get("class_counts")
    if not isinstance(counts, dict) or not counts:
        return None

    numeric = {k: v for k, v in counts.items() if isinstance(v, (int, float))}
    if not numeric:
        return None

    ordered = sorted(numeric.items(), key=lambda kv: kv[1], reverse=True)
    if len(ordered) <= limit:
        shown = ordered
        note = ""
    else:
        half = limit // 2
        shown = ordered[:half] + ordered[-half:]
        note = f" (showing the {half} most and {half} least common of {len(ordered)})"

    body = ", ".join(f"{name}: {int(count)}" for name, count in shown)
    return f"Instances per class{note}: {body}"


def _safely(label: str, fn, fallback):
    """Run one context lookup, trading a failed source for a missing fact.

    The context is assembled from four independent sources and any of them can
    be absent on a young project or briefly unavailable. Losing one fact is
    acceptable; losing the whole answer is not.
    """
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - context is best-effort by design
        logger.warning("Assistant context: could not read %s: %s", label, e)
        return fallback


def _dataset_lines(dataset: Dict) -> List[str]:
    classes = dataset.get("classes") or []
    total = dataset.get("total_images") or 0
    annotated = dataset.get("annotated_images") or 0
    return [
        f"Project: {dataset.get('name')}",
        f"Classes ({len(classes)}): {', '.join(classes) if classes else 'none'}",
        f"Images: {total} uploaded, {annotated} annotated, "
        f"{max(0, total - annotated)} still unlabelled",
    ]


def _stats_lines(stats: Dict) -> List[str]:
    lines = []
    balance = _class_balance(stats)
    if balance:
        lines.append(balance)
    for key, label in (
        ("train_count", "train"),
        ("val_count", "val"),
        ("test_count", "test"),
    ):
        if isinstance(stats.get(key), int):
            lines.append(f"Split {label}: {stats[key]} images")
    return lines


def _version_lines(versions: List[Dict]) -> List[str]:
    if not versions:
        # Said explicitly, because "you cannot train yet" is the correct answer
        # to a lot of questions and silence would not convey it.
        return ["Frozen versions: none — nothing can be trained until one exists"]
    latest = versions[-1]
    return [
        f"Frozen versions: {len(versions)}; latest is v{latest.get('version_number')} "
        f"({latest.get('task') or 'detect'} task, {latest.get('total_images')} images)"
    ]


def _health_lines(health: Optional[Dict]) -> List[str]:
    if not isinstance(health, dict):
        return []

    lines = []
    score = health.get("overall_quality_score")
    if score is not None:
        lines.append(f"Health score: {score}")
    for key, label in (
        ("duplicate_count", "exact duplicates"),
        ("near_duplicate_count", "near-duplicates"),
        ("blurry_count", "blurry images"),
        ("corrupt_count", "corrupt images"),
    ):
        value = health.get(key)
        # A zero count is not a finding; listing it would only pad the prompt.
        if isinstance(value, int) and value > 0:
            lines.append(f"Health: {value} {label}")
    issues = health.get("issues") or health.get("warnings")
    if isinstance(issues, list) and issues:
        lines.append("Health issues: " + "; ".join(str(i) for i in issues[:5]))
    return lines


def _run_lines(run: Optional[Dict]) -> List[str]:
    if not run:
        return ["Latest run: none yet"]

    results = run.get("results") or {}
    if run.get("status") != "completed":
        return [
            f"Latest run: {run.get('model_name')} FAILED — "
            f"{(run.get('error_message') or 'no error recorded')[:300]}"
        ]

    metrics = results.get("metrics") or {}
    summary = ", ".join(
        f"{k} {v:.3f}" for k, v in metrics.items() if isinstance(v, (int, float))
    )
    lines = [
        f"Latest run: {run.get('model_name')} completed "
        f"({run.get('epochs')} epochs) — {summary or 'no metrics recorded'}"
    ]

    # The weakest classes are usually the answer to "why is my mAP low", so
    # they are named rather than left for the user to go and look up.
    weakest = sorted(
        (
            c
            for c in (results.get("per_class_metrics") or [])
            if isinstance(c.get("mAP50"), (int, float))
        ),
        key=lambda c: c["mAP50"],
    )[:5]
    if weakest:
        lines.append(
            "Weakest classes by mAP50: "
            + ", ".join(f"{c.get('class_name')} {c['mAP50']:.3f}" for c in weakest)
        )
    return lines


def build_project_context(dataset_id: str) -> str:
    """Assemble the facts about one project that an answer can be grounded in."""
    dataset = _safely("dataset", lambda: DatasetService.get_dataset(dataset_id), None)
    if not dataset:
        return ""

    stats = _safely(
        "stats", lambda: AnnotationService.get_dataset_stats(dataset_id) or {}, {}
    )
    versions = _safely(
        "versions", lambda: DatasetVersionService.list_dataset_versions(dataset_id) or [], []
    )
    health = _safely(
        "health snapshot", lambda: QualitySnapshotService.get_latest_snapshot(dataset_id), None
    )
    run = _safely("latest run", lambda: _latest_run(dataset_id), None)

    lines = (
        _dataset_lines(dataset)
        + _stats_lines(stats)
        + _version_lines(versions)
        + _health_lines(health)
        + _run_lines(run)
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------


def rule_based_reply(last_message: str) -> str:
    """The answers available without a model.

    Kept from the original mock, with the two references to tabs that never
    existed ("Monitor tab" for logs, "Help & Contact") corrected to real ones.
    Returns the answer alone — the caller appends why it is answering this way,
    since "no model configured" and "the model could not be reached" are
    different situations and the old single trailing note fitted only one.
    """
    text = (last_message or "").lower()

    if "train" in text or "model" in text:
        answer = (
            "Training runs against a frozen version, not the live dataset. Freeze one "
            "in the Generate tab, then pick a backend and version in Train and run "
            "preflight before starting the job."
        )
    elif "dataset" in text or "upload" in text:
        answer = (
            "Create a project from the dashboard, then add images in its Upload tab — "
            "drag them in, import a ZIP, or extract frames from a video."
        )
    elif "annotate" in text or "label" in text:
        answer = (
            "Draw boxes or polygons in the Annotate tab. Auto-label from an existing "
            "model and correct the results, or use the segment-assisted tools, then "
            "propagate boxes across similar images."
        )
    elif "deploy" in text or "api" in text:
        answer = (
            "Once a run finishes, the Deploy tab exports the weights (pt, onnx, engine, "
            "coreml) and shows how to call the model with an API key."
        )
    elif "class" in text:
        answer = (
            "The Classes tab renames, adds, merges and deletes classes across the whole "
            "dataset, with the instance count for each."
        )
    elif "error" in text or "fail" in text:
        answer = (
            "For a failed run, open the Registry tab and read the run's log. For a model "
            "that trained but predicts badly, the Evaluate tab says how each prediction "
            "is wrong — hallucinated, wrong-class, loose-box, duplicate or missed."
        )
    else:
        answer = (
            "I can help with uploading, annotating, versioning, training, evaluating and "
            "deploying in this project."
        )

    return answer


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------


def _conversation(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Keep the recent user/assistant turns, starting at a user message.

    The API requires the first message to be from the user, so a window that
    happens to begin on an assistant turn is trimmed rather than sent.
    """
    cleaned = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]
    window = cleaned[-MAX_HISTORY_TURNS:]
    while window and window[0]["role"] != "user":
        window.pop(0)
    return window


def answer(messages: List[Dict[str, str]], project_context: str = "") -> str:
    """Ask the model, with the project's own numbers in the system prompt.

    Raises AssistantUnavailable if the model could not be reached, so the
    endpoint can fall back rather than returning an error to the widget.
    """
    conversation = _conversation(messages)
    if not conversation:
        raise AssistantUnavailable("No usable messages in the request")

    if project_context:
        system = SYSTEM_PROMPT + "\n" + GROUNDING_PROMPT.format(context=project_context)
    else:
        system = SYSTEM_PROMPT + "\n" + NO_CONTEXT_PROMPT
    # Not cached: the stable half of this prompt is a few hundred tokens, well
    # under the smallest cacheable prefix, so a breakpoint here would never be
    # a hit and would only read as if caching were happening.

    response = _call_model(system, conversation)

    # Checked before reading content: on a refusal the content blocks carry no
    # answer, so indexing into them would surface an empty reply.
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        logger.info("Assistant request declined (category=%s)", category)
        raise AssistantUnavailable("The assistant declined to answer that")

    text = "\n".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    if not text:
        raise AssistantUnavailable("The assistant returned an empty response")
    return text


def _call_model(system: str, conversation: List[Dict[str, str]]):
    """One Messages request, with every failure mode mapped to a fallback signal.

    Split out from `answer` so the exception chain stays specific — a single
    broad `except APIStatusError` would lose the difference between a bad key,
    a missing model and a transient 503, which are the three things an operator
    needs told apart.
    """
    import anthropic

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key or None,
        timeout=60.0,
    )

    try:
        return client.beta.messages.create(
            model=settings.assistant_model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=conversation,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            # A policy decline would otherwise end the turn with no answer;
            # this re-runs the same request on the fallback model in-call.
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
        )
    except anthropic.AuthenticationError as e:
        raise AssistantUnavailable("The configured API key was rejected") from e
    except anthropic.PermissionDeniedError as e:
        raise AssistantUnavailable("The configured API key lacks permission") from e
    except anthropic.NotFoundError as e:
        raise AssistantUnavailable(
            f"Model '{settings.assistant_model}' is not available to this key"
        ) from e
    except anthropic.RateLimitError as e:
        raise AssistantUnavailable("Rate limited — try again shortly") from e
    except anthropic.APIStatusError as e:
        raise AssistantUnavailable(f"Assistant API error ({e.status_code})") from e
    except anthropic.APIConnectionError as e:
        raise AssistantUnavailable("Could not reach the assistant API") from e


class AssistantUnavailable(RuntimeError):
    """The model could not answer — the caller should fall back."""
