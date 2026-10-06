"""
Webhook validation, signing, delivery and throttling.

The URL check is the security-relevant part: any project admin can register a
hook, and the server will POST to whatever they give it, so without the
address check a webhook is a request-forgery primitive aimed at the
deployment's own network.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
import requests

from app.services import webhooks
from app.services.webhooks import WebhookValidationError

# --- URL validation --------------------------------------------------------


def _resolving_to(*addresses):
    """Patch name resolution so the test never touches real DNS."""
    import ipaddress

    return patch.object(
        webhooks,
        "_resolved_addresses",
        lambda host: [ipaddress.ip_address(a) for a in addresses],
    )


def test_a_public_https_url_is_accepted():
    with _resolving_to("93.184.216.34"):
        assert webhooks.validate_url("https://hooks.example.com/x") == (
            "https://hooks.example.com/x"
        )


def test_whitespace_is_trimmed():
    with _resolving_to("93.184.216.34"):
        assert webhooks.validate_url("  https://hooks.example.com/x  ").startswith("https")


def test_http_is_rejected():
    # The payload describes the project's data, so it does not travel in clear.
    with pytest.raises(WebhookValidationError, match="https"):
        webhooks.validate_url("http://hooks.example.com/x")


@pytest.mark.parametrize("url", ["", "   ", "https://", "not-a-url"])
def test_unusable_urls_are_rejected(url):
    with pytest.raises(WebhookValidationError):
        webhooks.validate_url(url)


def test_an_overlong_url_is_rejected():
    with pytest.raises(WebhookValidationError, match="2000 characters"):
        webhooks.validate_url("https://example.com/" + "a" * 2100)


@pytest.mark.parametrize(
    "address,label",
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.5", "private class A"),
        ("192.168.1.10", "private class C"),
        ("172.16.4.4", "private class B"),
        ("169.254.169.254", "cloud metadata"),
        ("0.0.0.0", "unspecified"),
        ("224.0.0.1", "multicast"),
        ("::1", "IPv6 loopback"),
        ("fe80::1", "IPv6 link-local"),
    ],
)
def test_non_public_targets_are_refused(address, label):
    # A public hostname is free to resolve to any of these, which is exactly
    # the case the check exists for — the name alone proves nothing.
    with _resolving_to(address):
        with pytest.raises(WebhookValidationError, match="non-public"):
            webhooks.validate_url("https://totally-public-name.example.com/x")


def test_a_host_with_one_private_answer_is_refused():
    # DNS can return several addresses; one reachable internal address is
    # enough to make the hook useful for forgery.
    with _resolving_to("93.184.216.34", "10.1.2.3"):
        with pytest.raises(WebhookValidationError, match="non-public"):
            webhooks.validate_url("https://mixed.example.com/x")


def test_an_unresolvable_host_is_refused_with_the_reason():
    # Patch resolution at the socket boundary, so this covers the wrapping in
    # _resolved_addresses rather than just the stub.
    import socket

    with patch.object(
        webhooks.socket, "getaddrinfo", side_effect=socket.gaierror("unknown host")
    ):
        with pytest.raises(WebhookValidationError, match="Could not resolve"):
            webhooks.validate_url("https://nope.invalid/x")


def test_a_host_resolving_to_nothing_usable_is_accepted_as_public():
    # getaddrinfo answered, but with nothing parseable as an address. There is
    # no private address to object to, so this is not the check's business.
    with patch.object(webhooks.socket, "getaddrinfo", return_value=[]):
        assert webhooks.validate_url("https://odd.example.com/x").endswith("/x")


# --- event subscriptions ---------------------------------------------------


def test_events_are_normalised_to_registry_order():
    assert webhooks.validate_events(["drift.detected", "training.completed"]) == [
        "training.completed",
        "drift.detected",
    ]


def test_a_single_event_string_is_accepted():
    assert webhooks.validate_events("training.failed") == ["training.failed"]


def test_duplicate_events_collapse():
    assert webhooks.validate_events(["training.failed", "training.failed"]) == [
        "training.failed"
    ]


def test_an_empty_subscription_is_rejected():
    with pytest.raises(WebhookValidationError, match="at least one event"):
        webhooks.validate_events([])


def test_an_unknown_event_is_rejected_at_save_time():
    # Otherwise the hook saves cleanly and silently never fires.
    with pytest.raises(WebhookValidationError, match="training.finished"):
        webhooks.validate_events(["training.finished"])


# --- signing ---------------------------------------------------------------


def test_signature_is_hmac_sha256_of_the_exact_body():
    body = b'{"event":"training.completed"}'
    expected = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert webhooks.sign("topsecret", body) == expected


def test_signature_changes_with_the_body():
    assert webhooks.sign("k", b"a") != webhooks.sign("k", b"b")


def test_signature_changes_with_the_secret():
    assert webhooks.sign("k1", b"a") != webhooks.sign("k2", b"a")


# --- delivery --------------------------------------------------------------


HOOK = {
    "id": "hook-1",
    "dataset_id": "ds-1",
    "url": "https://hooks.example.com/x",
    "secret": "shh",
}


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Delivery records its outcome; these tests have no database."""
    monkeypatch.setattr(webhooks, "_record_attempt", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(webhooks.time, "sleep", lambda _s: None)


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def test_a_2xx_is_a_successful_delivery():
    with patch.object(webhooks.requests, "post", return_value=_Response(200)) as post:
        assert webhooks.deliver(HOOK, "training.completed", {"a": 1}, "d1") is True
    assert post.call_count == 1


def test_the_signed_body_matches_the_signature_header():
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["data"] = data
        captured["headers"] = headers
        return _Response(204)

    with patch.object(webhooks.requests, "post", fake_post):
        assert webhooks.deliver(HOOK, "drift.detected", {"severity": "high"}, "d2") is True

    signature = captured["headers"][webhooks.SIGNATURE_HEADER]
    assert signature == f"sha256={webhooks.sign('shh', captured['data'])}"
    # A receiver verifies the bytes it was given, so the envelope has to be
    # recoverable from exactly those bytes.
    envelope = json.loads(captured["data"])
    assert envelope["event"] == "drift.detected"
    assert envelope["delivery_id"] == "d2"
    assert envelope["data"] == {"severity": "high"}
    assert captured["headers"][webhooks.EVENT_HEADER] == "drift.detected"


def test_a_5xx_is_retried_to_the_attempt_limit():
    with patch.object(webhooks.requests, "post", return_value=_Response(500)) as post:
        assert webhooks.deliver(HOOK, "training.completed", {}, "d3") is False
    assert post.call_count == webhooks.MAX_ATTEMPTS


def test_a_4xx_is_not_retried():
    # The receiver rejected the payload itself; replaying it unchanged gets
    # the same answer and just burns timeouts.
    with patch.object(webhooks.requests, "post", return_value=_Response(400)) as post:
        assert webhooks.deliver(HOOK, "training.completed", {}, "d4") is False
    assert post.call_count == 1


def test_a_429_is_retried_even_though_it_is_a_4xx():
    with patch.object(webhooks.requests, "post", return_value=_Response(429)) as post:
        assert webhooks.deliver(HOOK, "training.completed", {}, "d5") is False
    assert post.call_count == webhooks.MAX_ATTEMPTS


def test_a_connection_error_is_retried_and_does_not_escape():
    # deliver() runs on a pool thread, where an exception would be swallowed.
    with patch.object(
        webhooks.requests, "post", side_effect=requests.ConnectionError("refused")
    ) as post:
        assert webhooks.deliver(HOOK, "training.failed", {}, "d6") is False
    assert post.call_count == webhooks.MAX_ATTEMPTS


def test_recovery_after_failures_still_succeeds():
    responses = [_Response(503), _Response(200)]
    with patch.object(webhooks.requests, "post", side_effect=responses):
        assert webhooks.deliver(HOOK, "training.completed", {}, "d7") is True


# --- throttling ------------------------------------------------------------


@pytest.fixture
def _clear_throttle():
    webhooks._last_emitted.clear()
    yield
    webhooks._last_emitted.clear()


def test_a_polled_event_is_emitted_once_per_window(_clear_throttle, monkeypatch):
    calls = []
    monkeypatch.setattr(
        webhooks, "emit", lambda ds, ev, pl: calls.append((ds, ev)) or 1
    )

    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 3600) == 1
    # The monitoring tab polls; every later read inside the window is silent.
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 3600) == 0
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 3600) == 0
    assert len(calls) == 1


def test_throttling_is_per_dataset(_clear_throttle, monkeypatch):
    monkeypatch.setattr(webhooks, "emit", lambda ds, ev, pl: 1)
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 3600) == 1
    assert webhooks.emit_throttled("ds-2", "drift.detected", {}, 3600) == 1


def test_a_zero_cooldown_does_not_suppress(_clear_throttle, monkeypatch):
    monkeypatch.setattr(webhooks, "emit", lambda ds, ev, pl: 1)
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 0) == 1
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 0) == 1


def test_nothing_is_suppressed_when_there_were_no_hooks(_clear_throttle, monkeypatch):
    """A hook added later must not have to wait out a window it never saw."""
    monkeypatch.setattr(webhooks, "emit", lambda ds, ev, pl: 0)
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 3600) == 0

    monkeypatch.setattr(webhooks, "emit", lambda ds, ev, pl: 1)
    assert webhooks.emit_throttled("ds-1", "drift.detected", {}, 3600) == 1


def test_emit_without_a_dataset_does_nothing(monkeypatch):
    # A job row missing its dataset_id should not reach the database.
    def fail(*a, **k):
        raise AssertionError("should not query")

    monkeypatch.setattr(webhooks, "_subscribed", fail)
    assert webhooks.emit(None, "training.completed", {}) == 0
    assert webhooks.emit("", "training.completed", {}) == 0


def test_emit_survives_a_database_failure(monkeypatch):
    """The caller is a training completion handler; it must not be broken."""

    def boom(dataset_id, event):
        raise RuntimeError("Database connection unavailable")

    monkeypatch.setattr(webhooks, "_subscribed", boom)
    assert webhooks.emit("ds-1", "training.completed", {}) == 0
