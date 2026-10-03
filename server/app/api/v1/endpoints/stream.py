"""
Live inference over a WebSocket.

The Test tab could run a model against uploaded images one POST at a time. A
webcam needs something else: each frame carries the TLS and auth cost of a
fresh request, and HTTP gives no way to say "skip the frames that piled up
while I was busy" — so a slow model turns into visible, compounding lag.

This holds one socket, one loaded model, and applies a single rule:

    **latest frame wins.**

While a frame is being scored, anything that arrives is dropped except the
newest one. That trades frames for latency, which is the right trade for a
live preview: the user wants boxes on *now*, not a faithful rendering of two
seconds ago. Dropped frames are counted and reported so the client can show
an honest effective FPS.

Auth note: browsers cannot set an Authorization header on a WebSocket, so the
token arrives as a query parameter — the same concession `GET /image/...`
already makes for `<img src>`. A credential in a URL is a real cost; it is
accepted here for the same reason and no further.
"""

import asyncio
import base64
import binascii
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.access import effective_role
from app.core.rbac import decode_access_token
from app.services.database import DatasetService

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[4]
_RUNS_BASE = (_SERVER_ROOT / "runs" / "detect").resolve()

# A frame larger than this is almost certainly a mistake (a full-resolution
# PNG rather than a downscaled JPEG), and decoding it would stall the loop.
MAX_FRAME_BYTES = 4 * 1024 * 1024

# Close codes. 1008 is "policy violation", which is the closest standard code
# for an auth or authorisation failure.
WS_POLICY_VIOLATION = 1008
WS_INTERNAL_ERROR = 1011

# Guard against a client that opens a socket and never sends anything.
IDLE_TIMEOUT_SECONDS = 120


def _resolve_weights(job_id: str) -> Optional[Path]:
    """Locate a job's weights, with the usual containment check."""
    weights_dir = (_RUNS_BASE / f"job_{job_id}" / "weights").resolve()
    if not str(weights_dir).startswith(str(_RUNS_BASE)):
        return None
    for name in ("best.pt", "last.pt"):
        candidate = weights_dir / name
        if candidate.exists():
            return candidate
    return None


def _authorise(token: Optional[str], dataset_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolve the token and check the caller may read this dataset.

    Returns the token payload, or None for any failure — the caller turns that
    into a close, without telling an unauthenticated client which of the two
    things went wrong.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None

    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        return None
    if not effective_role(dataset_id, payload["user_id"], dataset["user_id"]):
        return None
    return payload


def _pil_open():
    """
    PIL's own `Image.open`, bypassing ultralytics' wrapper.

    Importing ultralytics monkey-patches `PIL.Image.open` so that *any* failure
    triggers `check_requirements("pi-heif")` — which attempts a pip install
    over the network before re-raising. On a machine without pi-heif that turns
    one malformed frame into roughly thirteen seconds of blocking, which on a
    live stream is the difference between dropping a frame and stalling the
    worker. Frames here are never HEIF (a browser canvas emits JPEG or PNG), so
    the wrapper buys nothing and costs a great deal.

    `_image_open` is the original PIL function, which the patch module keeps a
    reference to. Falling back to the patched one is still correct — just slow
    on bad input — so a future ultralytics that drops that name degrades rather
    than breaking.
    """
    try:
        from ultralytics.utils.patches import _image_open

        return _image_open
    except Exception:
        from PIL import Image as PILImage

        return PILImage.open


def _decode_frame(data: str) -> Optional[Any]:
    """
    Turn a base64 data URL (or bare base64) into a PIL image.

    Returns None for anything undecodable; a bad frame should cost one frame,
    not the session.
    """
    payload = data.split(",", 1)[1] if data.startswith("data:") else data
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None

    if not raw or len(raw) > MAX_FRAME_BYTES:
        return None

    try:
        image = _pil_open()(BytesIO(raw))
        # Decode now, inside the guard: PIL is lazy, so a truncated file would
        # otherwise raise later, in the inference call.
        image.load()
        return image.convert("RGB")
    except Exception:
        return None


class _FrameMailbox:
    """
    A one-slot mailbox fed by a background reader: latest frame wins.

    Implemented this way rather than by draining the socket inline, because
    cancelling a half-completed `receive_json()` — which is what an inline
    `timeout=0` drain does — can lose a message or leave the connection in a
    state starlette does not expect. The reader never cancels a receive; it
    overwrites the slot, and the overwrite *is* the frame drop.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._latest: Optional[Dict[str, Any]] = None
        self._arrived = asyncio.Event()
        self.dropped = 0
        self.closed = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._read_forever())

    async def _read_forever(self) -> None:
        try:
            while True:
                message = await self._websocket.receive_json()
                kind = message.get("type")
                if kind == "close":
                    break
                if kind != "frame":
                    continue
                if self._latest is not None:
                    # The frame already waiting never got scored.
                    self.dropped += 1
                self._latest = message
                self._arrived.set()
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as e:
            logger.warning(f"live inference reader stopped: {e}")
        finally:
            self.closed = True
            self._arrived.set()

    async def next_frame(self, timeout: float) -> Optional[Dict[str, Any]]:
        """
        The newest frame, or None when the client has gone or nothing came.

        Raises asyncio.TimeoutError if nothing arrives within `timeout`, which
        the caller treats as an idle connection.
        """
        await asyncio.wait_for(self._arrived.wait(), timeout=timeout)
        frame, self._latest = self._latest, None
        self._arrived.clear()
        return frame

    async def stop(self) -> None:
        """Cancel the reader and wait for it, so it cannot outlive the socket."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass


async def _score_frame(
    websocket: WebSocket,
    model: Any,
    message: Dict[str, Any],
    confidence: float,
) -> bool:
    """
    Decode, score and reply for one frame. Returns True if it was scored.

    A frame that cannot be decoded or that inference throws on costs that one
    frame and an error message — never the session.
    """
    image = _decode_frame(message.get("data") or "")
    if image is None:
        await websocket.send_json(
            {"type": "error", "message": "Could not decode that frame."}
        )
        return False

    # Read the dimensions before inference: the image is closed afterwards,
    # and the client needs them to scale its overlay.
    width, height = image.width, image.height

    started = time.perf_counter()
    try:
        # Inference is blocking and CPU/GPU-bound; off the event loop it goes,
        # or the reader cannot keep draining while it runs.
        detections = await asyncio.to_thread(model.predict, image, confidence)
    except Exception as e:
        logger.warning(f"live inference failed on a frame: {e}")
        await websocket.send_json(
            {"type": "error", "message": "Inference failed on that frame."}
        )
        return False
    finally:
        image.close()

    await websocket.send_json({
        "type": "detections",
        "detections": [
            {
                "class_id": d.get("class_id"),
                "class_name": d.get("class_name"),
                "confidence": round(float(d.get("confidence", 0)), 4),
                "bbox": [round(float(v), 1) for v in (d.get("bbox") or [])],
            }
            for d in detections
        ],
        "width": width,
        "height": height,
        "inference_ms": round((time.perf_counter() - started) * 1000, 1),
    })
    return True


async def _handshake(
    websocket: WebSocket,
    dataset_id: str,
    job_id: str,
    token: Optional[str],
) -> Optional[Any]:
    """
    Authorise, locate the weights and load the model.

    Returns the loaded model, or None having already closed the socket with a
    reason. Every failure path accepts the connection before closing it, so the
    browser surfaces a readable close code rather than an opaque handshake
    failure it cannot inspect.
    """
    if not _authorise(token, dataset_id):
        await websocket.accept()
        await websocket.close(
            code=WS_POLICY_VIOLATION, reason="Not authorised for this dataset"
        )
        return None

    weights = _resolve_weights(job_id)
    if weights is None:
        await websocket.accept()
        await websocket.close(
            code=WS_POLICY_VIOLATION, reason="No trained weights for that job"
        )
        return None

    await websocket.accept()

    # Load the model once per connection. This is the whole latency argument
    # for holding a socket open: a per-frame POST pays the model lookup on
    # every single frame.
    try:
        from app.services.inference import YOLOInference

        model = await asyncio.to_thread(YOLOInference, str(weights))
    except Exception as e:
        logger.error(f"live inference: could not load {weights}: {e}")
        await websocket.close(code=WS_INTERNAL_ERROR, reason="Could not load the model")
        return None

    await websocket.send_json({
        "type": "ready",
        "model": weights.name,
        "job_id": job_id,
        "device": getattr(model, "device", "cpu"),
    })
    return model


@router.websocket("/live")
async def live_inference(
    websocket: WebSocket,
    dataset_id: str = Query(...),
    job_id: str = Query(...),
    token: Optional[str] = Query(None),
    confidence: float = Query(0.25, ge=0.0, le=1.0),
):
    """
    Score frames as they arrive.

    Client sends `{"type": "frame", "data": "<base64 jpeg>"}`; the server
    replies `{"type": "detections", ...}` per frame it actually scored. Send
    `{"type": "close"}` to finish cleanly.
    """
    model = await _handshake(websocket, dataset_id, job_id, token)
    if model is None:
        return

    mailbox = _FrameMailbox(websocket)
    mailbox.start()
    scored = 0

    try:
        while True:
            try:
                frame = await mailbox.next_frame(IDLE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await websocket.close(code=1000, reason="Idle")
                return

            if frame is None:
                # Woken with an empty slot: the client closed or disconnected.
                if mailbox.closed:
                    return
                continue

            if await _score_frame(websocket, model, frame, confidence):
                scored += 1
                # Sent separately from the detections so the client can show the
                # FPS the model actually managed, rather than the capture rate.
                await websocket.send_json({
                    "type": "stats",
                    "scored": scored,
                    "dropped": mailbox.dropped,
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"live inference loop failed: {e}")
        try:
            await websocket.close(code=WS_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        await mailbox.stop()
        logger.info(
            f"live inference closed: {scored} frame(s) scored, "
            f"{mailbox.dropped} dropped"
        )
