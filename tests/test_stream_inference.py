"""Tests for live WebSocket inference.

Two things are worth guarding without a real model or camera: the frame
decoder (it is the only place untrusted bytes enter the loop) and the
handshake's authorisation, since a WebSocket carries its token in the URL and
so has its own auth path rather than the usual dependency.

The mailbox's latest-frame-wins behaviour is exercised directly rather than
through a socket, because what matters is the drop accounting.
"""

import asyncio
import base64
from io import BytesIO

import pytest
from app.api.v1.endpoints import stream
from fastapi.testclient import TestClient
from main import app
from PIL import Image

client = TestClient(app, raise_server_exceptions=False)


def _jpeg_bytes(size=(32, 24), colour=(120, 60, 200)):
    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def test_the_websocket_route_is_registered():
    from starlette.routing import WebSocketRoute

    paths = []
    for route in app.routes:
        for candidate in getattr(route, "routes", [route]):
            if isinstance(candidate, WebSocketRoute):
                paths.append(candidate.path)
    assert "/api/stream/live" in paths


# ---------------------------------------------------------------------------
# Frame decoding — the only place untrusted bytes enter the loop
# ---------------------------------------------------------------------------

def test_a_bare_base64_jpeg_decodes():
    image = stream._decode_frame(_b64(_jpeg_bytes()))
    assert image is not None
    assert (image.width, image.height) == (32, 24)
    assert image.mode == "RGB"


def test_a_data_url_decodes():
    """Canvas.toDataURL() produces this shape, so it must be accepted."""
    image = stream._decode_frame(f"data:image/jpeg;base64,{_b64(_jpeg_bytes())}")
    assert image is not None
    assert image.width == 32


def test_a_greyscale_frame_is_converted_to_rgb():
    buffer = BytesIO()
    Image.new("L", (16, 16), 128).save(buffer, format="JPEG")
    image = stream._decode_frame(_b64(buffer.getvalue()))
    assert image is not None
    assert image.mode == "RGB"


@pytest.mark.parametrize(
    "payload",
    [
        "",                       # nothing
        "not base64 at all!!",    # undecodable
        _b64(b"neither a jpeg nor a png"),  # decodes, but is not an image
    ],
)
def test_a_bad_frame_decodes_to_none_rather_than_raising(payload):
    """A bad frame must cost one frame, not the session."""
    assert stream._decode_frame(payload) is None


def test_a_truncated_image_is_rejected_at_decode_time():
    """PIL is lazy, so without an explicit load() this would raise later —
    inside the inference call, where it would look like a model failure."""
    truncated = _jpeg_bytes(size=(200, 200))[:120]
    assert stream._decode_frame(_b64(truncated)) is None


def test_an_oversized_frame_is_rejected_before_decoding():
    """Decoding a full-resolution frame would stall the event loop."""
    oversized = _b64(b"\xff" * (stream.MAX_FRAME_BYTES + 1))
    assert stream._decode_frame(oversized) is None


# ---------------------------------------------------------------------------
# Handshake authorisation
# ---------------------------------------------------------------------------

def test_a_missing_token_is_not_authorised():
    assert stream._authorise(None, "ds-1") is None
    assert stream._authorise("", "ds-1") is None


def test_an_invalid_token_is_not_authorised():
    assert stream._authorise("not-a-jwt", "ds-1") is None


def test_a_valid_token_for_an_unknown_dataset_is_not_authorised(monkeypatch):
    monkeypatch.setattr(stream, "decode_access_token", lambda t: {"user_id": 1})
    monkeypatch.setattr(
        stream.DatasetService, "get_dataset", staticmethod(lambda d: None)
    )
    assert stream._authorise("good-token", "ds-1") is None


def test_a_valid_token_without_a_role_on_the_dataset_is_not_authorised(monkeypatch):
    monkeypatch.setattr(stream, "decode_access_token", lambda t: {"user_id": 1})
    monkeypatch.setattr(
        stream.DatasetService,
        "get_dataset",
        staticmethod(lambda d: {"id": d, "user_id": 999}),
    )
    monkeypatch.setattr(stream, "effective_role", lambda *a: None)
    assert stream._authorise("good-token", "ds-1") is None


def test_a_valid_token_with_a_role_is_authorised(monkeypatch):
    monkeypatch.setattr(stream, "decode_access_token", lambda t: {"user_id": 1})
    monkeypatch.setattr(
        stream.DatasetService,
        "get_dataset",
        staticmethod(lambda d: {"id": d, "user_id": 999}),
    )
    monkeypatch.setattr(stream, "effective_role", lambda *a: "viewer")
    assert stream._authorise("good-token", "ds-1") == {"user_id": 1}


def test_an_unauthorised_socket_is_closed_with_a_policy_code():
    """Accept-then-close, so the browser can read why instead of seeing an
    opaque handshake failure."""
    from fastapi import WebSocketDisconnect

    url = "/api/stream/live?dataset_id=ds-1&job_id=job-1&token=bogus"
    with client.websocket_connect(url) as socket, pytest.raises(WebSocketDisconnect) as closed:
        socket.receive_json()

    assert closed.value.code == stream.WS_POLICY_VIOLATION


# ---------------------------------------------------------------------------
# Weight resolution
# ---------------------------------------------------------------------------

def test_a_traversing_job_id_cannot_escape_the_runs_directory():
    assert stream._resolve_weights("../../../../etc") is None


def test_an_unknown_job_has_no_weights():
    assert stream._resolve_weights("job-that-never-ran") is None


# ---------------------------------------------------------------------------
# The mailbox: latest frame wins
# ---------------------------------------------------------------------------

class _FakeSocket:
    """Replays queued messages, then blocks forever like a quiet client."""

    def __init__(self, messages):
        self._messages = list(messages)

    async def receive_json(self):
        if self._messages:
            return self._messages.pop(0)
        await asyncio.Event().wait()  # never returns


def test_the_mailbox_keeps_only_the_newest_frame_and_counts_the_rest():
    """The point of the feature: a model slower than the capture rate must not
    build a queue, so superseded frames are dropped and counted."""

    async def scenario():
        mailbox = stream._FrameMailbox(
            _FakeSocket([
                {"type": "frame", "data": "first"},
                {"type": "frame", "data": "second"},
                {"type": "frame", "data": "third"},
            ])
        )
        mailbox.start()
        # Let the reader drain all three before anything is consumed, which is
        # exactly the backlog case.
        await asyncio.sleep(0.05)

        frame = await mailbox.next_frame(timeout=1)
        await mailbox.stop()
        return frame, mailbox.dropped

    frame, dropped = asyncio.run(scenario())
    assert frame["data"] == "third"
    assert dropped == 2


def test_the_mailbox_hands_over_a_single_frame_with_no_drops():
    async def scenario():
        mailbox = stream._FrameMailbox(
            _FakeSocket([{"type": "frame", "data": "only"}])
        )
        mailbox.start()
        frame = await mailbox.next_frame(timeout=1)
        await mailbox.stop()
        return frame, mailbox.dropped

    frame, dropped = asyncio.run(scenario())
    assert frame["data"] == "only"
    assert dropped == 0


def test_the_mailbox_ignores_messages_that_are_not_frames():
    async def scenario():
        mailbox = stream._FrameMailbox(
            _FakeSocket([
                {"type": "ping"},
                {"type": "nonsense"},
                {"type": "frame", "data": "real"},
            ])
        )
        mailbox.start()
        frame = await mailbox.next_frame(timeout=1)
        await mailbox.stop()
        return frame, mailbox.dropped

    frame, dropped = asyncio.run(scenario())
    assert frame["data"] == "real"
    # Non-frames never occupied the slot, so nothing was dropped.
    assert dropped == 0


def test_a_close_message_marks_the_mailbox_closed():
    async def scenario():
        mailbox = stream._FrameMailbox(_FakeSocket([{"type": "close"}]))
        mailbox.start()
        frame = await mailbox.next_frame(timeout=1)
        closed = mailbox.closed
        await mailbox.stop()
        return frame, closed

    frame, closed = asyncio.run(scenario())
    assert frame is None
    assert closed is True


def test_the_mailbox_times_out_on_a_silent_client():
    """A socket that opens and never sends must not be held open forever."""

    async def scenario():
        mailbox = stream._FrameMailbox(_FakeSocket([]))
        mailbox.start()
        try:
            with pytest.raises(asyncio.TimeoutError):
                await mailbox.next_frame(timeout=0.05)
        finally:
            await mailbox.stop()

    asyncio.run(scenario())


def test_a_disconnecting_reader_marks_the_mailbox_closed():
    """A dropped connection must wake the consumer, not leave it waiting."""

    class _Disconnecting:
        async def receive_json(self):
            from fastapi import WebSocketDisconnect

            raise WebSocketDisconnect(1000)

    async def scenario():
        mailbox = stream._FrameMailbox(_Disconnecting())
        mailbox.start()
        frame = await mailbox.next_frame(timeout=1)
        closed = mailbox.closed
        await mailbox.stop()
        return frame, closed

    frame, closed = asyncio.run(scenario())
    assert frame is None
    assert closed is True


# ---------------------------------------------------------------------------
# The ultralytics PIL patch
# ---------------------------------------------------------------------------

def test_decoding_bypasses_the_ultralytics_pil_wrapper():
    """Importing ultralytics replaces PIL.Image.open with a wrapper that, on
    any failure, tries to pip-install pi-heif before re-raising. The frame
    decoder must not go through it."""
    import PIL.Image

    resolved = stream._pil_open()
    try:
        from ultralytics.utils.patches import _image_open
    except ImportError:
        pytest.skip("ultralytics does not expose the original Image.open")

    assert resolved is _image_open
    # Only meaningful while ultralytics is actually patching PIL.
    if PIL.Image.open is not _image_open:
        assert resolved is not PIL.Image.open


def test_a_malformed_frame_is_rejected_promptly():
    """Regression guard on the above. Through the patched open this took
    ~13s per bad frame — long enough to stall a live stream — so the budget
    here is deliberately far below that and far above a real decode."""
    import time

    truncated = _jpeg_bytes(size=(200, 200))[:120]
    payload = _b64(truncated)

    started = time.perf_counter()
    assert stream._decode_frame(payload) is None
    assert time.perf_counter() - started < 2.0
