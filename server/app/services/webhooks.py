"""
Outbound webhooks for project events.

Training runs for minutes to hours, drift is detected on a schedule nobody is
watching, and auto-retrain fires from someone else's annotation save. All three
were observable only by having the UI open and polling — there was no way for
the platform to tell anyone that anything had happened.

A delivery is a POST of a JSON envelope, signed with HMAC-SHA256 over the exact
bytes sent so a receiver can verify it came from this deployment. Retries are
bounded and consecutive failures disable the hook, because a webhook pointing
at something that no longer exists otherwise retries forever on every event.

Deliveries run on a small thread pool, never inline. The most important
emitter is the training job's completion handler, which is itself already a
background task with no request scope to attach to — and a receiver that
hangs for the full timeout must not hold it open either way.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from app.db.session import db_cursor

logger = logging.getLogger(__name__)

# The events a hook can subscribe to. Kept as a closed set so a typo in a
# subscription is rejected at save time rather than silently never firing.
EVENTS = (
    "training.completed",
    "training.failed",
    "drift.detected",
    "autoretrain.triggered",
)

SIGNATURE_HEADER = "X-NebulaML-Signature"
EVENT_HEADER = "X-NebulaML-Event"
DELIVERY_HEADER = "X-NebulaML-Delivery"

REQUEST_TIMEOUT = 10  # seconds; a receiver slower than this is treated as down
MAX_ATTEMPTS = 3
RETRY_BACKOFF = (1, 4)  # seconds between attempts; len == MAX_ATTEMPTS - 1

# A hook that has failed this many times in a row is switched off. Something
# that has been gone for five consecutive events is not coming back on the
# sixth, and retrying forever turns every event into wasted timeouts.
MAX_CONSECUTIVE_FAILURES = 5

# Deliveries sleep between retries, so they cannot run on the event loop and
# must not run on the caller's thread. Bounded, because an unbounded pool lets
# a dead receiver and a burst of events spawn threads without limit.
_DISPATCH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")

# Some events are derived on read rather than raised by a state change. Drift
# is recomputed by a GET that the monitoring tab polls, so emitting on every
# detection would send one delivery per poll for as long as the drift lasts.
# A per-process cooldown collapses that into one notification per window.
#
# In-process, so it resets on restart and is per-worker under multiple
# workers: the guarantee is "not on every poll", not "exactly once".
DRIFT_COOLDOWN_SECONDS = 3600
_last_emitted: Dict[Tuple[str, str], float] = {}
_last_emitted_lock = threading.Lock()


class WebhookValidationError(ValueError):
    """A URL that will not be accepted — surfaced to the caller as a 400."""


def _resolved_addresses(host: str) -> List[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise WebhookValidationError(f"Could not resolve '{host}': {e}") from e

    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return addresses


def validate_url(url: str) -> str:
    """Accept only a public https endpoint.

    Any project admin can add a webhook, and the server fetches whatever URL
    they give it — so without this a webhook is a request-forgery primitive
    pointing at the deployment's own network: cloud metadata on
    169.254.169.254, an internal admin port on localhost, a database on a
    private address. The host is resolved here and every address it answers
    with is checked, because a public name can resolve to a private address.

    This cannot close the window completely — DNS can return a different
    answer at delivery time than it did at validation time — but it rejects
    the straightforward cases rather than none of them.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise WebhookValidationError("URL cannot be empty")
    if len(cleaned) > 2000:
        raise WebhookValidationError("URL must be 2000 characters or fewer")

    parsed = urlparse(cleaned)
    if parsed.scheme != "https":
        raise WebhookValidationError(
            "Webhook URLs must use https — the payload describes your project's data"
        )
    if not parsed.hostname:
        raise WebhookValidationError("URL has no host")

    for address in _resolved_addresses(parsed.hostname):
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise WebhookValidationError(
                f"'{parsed.hostname}' resolves to the non-public address {address}. "
                "Webhooks may only target public endpoints."
            )

    return cleaned


def validate_events(events) -> List[str]:
    """Normalise and check a subscription list."""
    if not events:
        raise WebhookValidationError("Subscribe to at least one event")
    if isinstance(events, str):
        events = [events]

    unknown = [e for e in events if e not in EVENTS]
    if unknown:
        raise WebhookValidationError(
            f"Unknown event(s): {', '.join(sorted(unknown))}. "
            f"Valid events are {', '.join(EVENTS)}."
        )
    # Preserve the declared order of EVENTS so stored rows are comparable.
    return [e for e in EVENTS if e in set(events)]


def sign(secret: str, body: bytes) -> str:
    """HMAC-SHA256 over the exact bytes sent, hex encoded.

    Signing the serialised body rather than re-serialising the payload is what
    lets a receiver verify without having to reproduce our JSON formatting.
    """
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def list_webhooks(dataset_id: str) -> List[Dict]:
    """Every hook on a project. The secret is never returned."""
    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            """
            SELECT id, dataset_id, url, events, enabled, created_at,
                   last_status, last_error, last_attempt_at, consecutive_failures
            FROM webhooks
            WHERE dataset_id = %s
            ORDER BY created_at ASC
            """,
            (dataset_id,),
        )
        rows = cursor.fetchall()

    for row in rows:
        try:
            row["events"] = json.loads(row["events"]) if row["events"] else []
        except (ValueError, TypeError):
            row["events"] = []
        row["enabled"] = bool(row["enabled"])
    return rows


def get_webhook(webhook_id: str) -> Optional[Dict]:
    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT id, dataset_id, url, secret, events, enabled FROM webhooks WHERE id = %s",
            (webhook_id,),
        )
        return cursor.fetchone()


def create_webhook(webhook_id: str, dataset_id: str, url: str, secret: str, events: List[str]) -> None:
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO webhooks (id, dataset_id, url, secret, events, enabled)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            """,
            (webhook_id, dataset_id, url, secret, json.dumps(events)),
        )


def update_webhook(
    webhook_id: str,
    url: Optional[str] = None,
    events: Optional[List[str]] = None,
    enabled: Optional[bool] = None,
) -> None:
    updates, values = [], []
    if url is not None:
        updates.append("url = %s")
        values.append(url)
    if events is not None:
        updates.append("events = %s")
        values.append(json.dumps(events))
    if enabled is not None:
        updates.append("enabled = %s")
        values.append(enabled)
        if enabled:
            # Re-enabling is the operator saying the receiver is fixed, so the
            # auto-disable counter starts over rather than disabling again on
            # the next failure.
            updates.append("consecutive_failures = 0")
    if not updates:
        return

    values.append(webhook_id)
    with db_cursor(commit=True) as cursor:
        cursor.execute(f"UPDATE webhooks SET {', '.join(updates)} WHERE id = %s", values)


def delete_webhook(webhook_id: str) -> None:
    with db_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM webhooks WHERE id = %s", (webhook_id,))


def _record_attempt(webhook_id: str, ok: bool, status: Optional[int], error: Optional[str]) -> None:
    """Store the outcome and disable a hook that keeps failing."""
    try:
        with db_cursor(commit=True) as cursor:
            if ok:
                cursor.execute(
                    """
                    UPDATE webhooks
                    SET last_status = %s, last_error = NULL,
                        last_attempt_at = CURRENT_TIMESTAMP, consecutive_failures = 0
                    WHERE id = %s
                    """,
                    (status, webhook_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE webhooks
                    SET last_status = %s, last_error = %s,
                        last_attempt_at = CURRENT_TIMESTAMP,
                        consecutive_failures = consecutive_failures + 1,
                        enabled = CASE
                            WHEN consecutive_failures + 1 >= %s THEN FALSE ELSE enabled
                        END
                    WHERE id = %s
                    """,
                    (status, (error or "")[:500], MAX_CONSECUTIVE_FAILURES, webhook_id),
                )
    except Exception as e:  # noqa: BLE001 - bookkeeping must not raise into a background task
        logger.warning("Could not record webhook attempt for %s: %s", webhook_id, e)


def deliver(webhook: Dict, event: str, payload: Dict, delivery_id: str) -> bool:
    """POST one event to one receiver, with bounded retries.

    Returns whether it was accepted. Never raises: this runs in a background
    task where an exception would be logged and lost, so failures are recorded
    on the webhook row instead, where the UI can show them.
    """
    body = json.dumps(
        {
            "event": event,
            "delivery_id": delivery_id,
            "dataset_id": webhook["dataset_id"],
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        },
        sort_keys=True,
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        EVENT_HEADER: event,
        DELIVERY_HEADER: delivery_id,
        SIGNATURE_HEADER: f"sha256={sign(webhook['secret'], body)}",
        "User-Agent": "NebulaML-Webhook/1",
    }

    status: Optional[int] = None
    error: Optional[str] = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.post(
                webhook["url"], data=body, headers=headers, timeout=REQUEST_TIMEOUT
            )
            status = response.status_code
            if 200 <= status < 300:
                _record_attempt(webhook["id"], True, status, None)
                return True
            error = f"HTTP {status}"
            # A 4xx other than 429 is the receiver rejecting the payload
            # itself; replaying it unchanged will be rejected the same way.
            if 400 <= status < 500 and status != 429:
                break
        except requests.RequestException as e:
            error = str(e)

        if attempt < len(RETRY_BACKOFF):
            time.sleep(RETRY_BACKOFF[attempt])

    logger.warning(
        "Webhook %s failed for %s: %s", webhook["id"], event, error
    )
    _record_attempt(webhook["id"], False, status, error)
    return False


def emit_throttled(
    dataset_id: str, event: str, payload: Dict, cooldown_seconds: int
) -> int:
    """`emit`, but at most once per dataset and event per cooldown window.

    For events observed by polling, where the condition persists across many
    reads and each read would otherwise be a separate notification.
    """
    if not dataset_id:
        return 0

    key = (dataset_id, event)
    now = time.monotonic()
    with _last_emitted_lock:
        previous = _last_emitted.get(key)
        if previous is not None and (now - previous) < cooldown_seconds:
            return 0
        # Stamped before dispatch, so concurrent polls cannot both get through.
        _last_emitted[key] = now

    queued = emit(dataset_id, event, payload)
    if queued == 0:
        # Nothing was sent, so nothing should be suppressed: a hook added
        # during the window would otherwise wait it out before its first event.
        with _last_emitted_lock:
            if _last_emitted.get(key) == now:
                _last_emitted.pop(key, None)
    return queued


def emit(dataset_id: str, event: str, payload: Dict) -> int:
    """Queue `event` to every enabled hook on the project subscribed to it.

    Returns how many deliveries were queued. Every caller is on a path whose
    real job is something else — finishing a training run, saving an
    annotation, answering a drift query — so this does no network I/O on the
    calling thread and raises nothing into it. A project with no hooks pays
    one indexed SELECT.
    """
    if not dataset_id:
        return 0

    try:
        hooks = _subscribed(dataset_id, event)
    except Exception as e:  # noqa: BLE001 - never break the caller
        logger.warning("Could not load webhooks for %s/%s: %s", dataset_id, event, e)
        return 0

    if not hooks:
        return 0

    for hook in hooks:
        try:
            _DISPATCH_POOL.submit(deliver, hook, event, payload, str(uuid.uuid4()))
        except RuntimeError as e:
            # Pool shut down during interpreter teardown.
            logger.warning("Could not dispatch webhook %s: %s", hook["id"], e)

    logger.info("Queued %d webhook deliveries for %s", len(hooks), event)
    return len(hooks)


def _subscribed(dataset_id: str, event: str) -> List[Dict]:
    """Enabled hooks on this project that asked for this event.

    The subscription filter is applied in Python rather than SQL because
    `events` is a JSON array and JSON_CONTAINS is not available on every MySQL
    build this runs against.
    """
    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            """
            SELECT id, dataset_id, url, secret, events
            FROM webhooks
            WHERE dataset_id = %s AND enabled = TRUE
            """,
            (dataset_id,),
        )
        rows = cursor.fetchall()

    subscribed = []
    for row in rows:
        try:
            events = json.loads(row["events"]) if row["events"] else []
        except (ValueError, TypeError):
            continue
        if event in events:
            subscribed.append(row)
    return subscribed
