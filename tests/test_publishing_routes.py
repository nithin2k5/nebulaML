"""Route tests for publishing, with the auth boundary as the subject.

This module introduced the application's only anonymous data path, so these
assert the boundary in both directions: management routes must reject an
unauthenticated caller, and the public routes must *not* require auth —
reaching a 404 for an unknown slug proves the handler ran rather than being
turned away at the door.

TestClient is built without a `with` block, following test_uncertainty_route,
so no database is needed to start the app.
"""

import inspect
import re

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import publishing as endpoints
from app.services import publishing as service
from main import app

client = TestClient(app, raise_server_exceptions=False)

MANAGEMENT = [
    ("post", "/api/publish"),
    ("get", "/api/publish/dataset/some-dataset"),
    ("patch", "/api/publish/some-publication"),
    ("delete", "/api/publish/some-publication"),
]

PUBLIC = [
    "/api/public/datasets/unknown-slug",
    "/api/public/datasets/unknown-slug/image/0",
    "/api/public/datasets/unknown-slug/download",
]


# ── Wiring ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [
    "/api/publish",
    "/api/publish/dataset/{dataset_id}",
    "/api/publish/{publication_id}",
    "/api/public/datasets/{slug}",
    "/api/public/datasets/{slug}/image/{index}",
    "/api/public/datasets/{slug}/download",
])
def test_route_is_registered(path):
    assert path in app.openapi()["paths"]


# ── The boundary ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method, url", MANAGEMENT)
def test_management_routes_reject_anonymous_callers(method, url):
    """Publishing, editing and revoking are never anonymous."""
    send = getattr(client, method)
    # httpx's get/delete take no body, so only the writers are given one.
    response = send(url, json={}) if method in ("post", "patch") else send(url)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("url", PUBLIC)
def test_public_routes_are_not_turned_away_at_the_door(url):
    """The slug must be sufficient: no 401, no 403.

    These tests run without a database, so an unknown slug surfaces as a 500
    from the lookup rather than the 404 it returns in a live instance. Either
    way the handler ran, which is the property under test — a 401 or 403 would
    mean authentication was demanded before the slug was even read.
    """
    response = client.get(url)
    assert response.status_code not in (401, 403), response.text


@pytest.mark.parametrize("url", PUBLIC)
def test_public_routes_are_reachable_without_a_token(url):
    """Sending no Authorization header at all must change nothing."""
    bare = client.get(url, headers={})
    assert bare.status_code not in (401, 403), bare.text


def test_a_missing_and_a_revoked_slug_answer_identically():
    """Probing must not distinguish a wrong slug from a withdrawn one.

    Checked on the source because telling the two apart needs two database
    states. Every public handler raises the same detail, and none of them
    mentions revocation.
    """
    for route in endpoints.public_router.routes:
        source = inspect.getsource(route.endpoint)
        # The messages themselves, not the prose around them — a comment
        # explaining the rule is not a violation of it.
        details = re.findall(r'detail=f?"([^"]*)"', source)
        assert details, f"{route.path} raises nothing a caller can see"

        not_found = [d for d in details if d.startswith("No such")]
        assert not_found, f"{route.path} has no not-found branch"

        for message in details:
            lowered = message.lower()
            for leak in ("revok", "withdraw", "taken down", "disabled by"):
                assert leak not in lowered, f"{route.path} says {message!r}"


def test_no_public_handler_depends_on_a_user():
    """A handler added to the public router without auth is world-readable.

    Asserted structurally rather than by example, so a future route cannot
    quietly join the anonymous surface while believing itself protected.
    """
    for route in endpoints.public_router.routes:
        source = inspect.getsource(route.endpoint)
        assert "current_user" not in source, f"{route.path} takes a user"
        assert "get_current_user" not in source, f"{route.path} authenticates"


def test_every_public_handler_is_rate_limited():
    """The slug is the only credential, so a leaked one must not be a tap."""
    for route in endpoints.public_router.routes:
        source = inspect.getsource(route.endpoint)
        assert "limiter.limit" in source, f"{route.path} has no rate limit"


def test_every_management_handler_requires_a_user():
    for route in endpoints.router.routes:
        source = inspect.getsource(route.endpoint)
        assert "current_user" in source, f"{route.path} takes no user"


def test_public_handlers_build_their_response_through_the_allowlist():
    """Public JSON comes from public_payload, never from a raw row."""
    source = inspect.getsource(endpoints.public_dataset_card)
    assert "public_payload" in source
    # No direct row return, which would ship every column.
    assert "return publication" not in source


# ── Request validation ───────────────────────────────────────────────────────


def _request(**overrides):
    payload = {
        "dataset_id": "d1",
        "version_id": "v1",
        "title": "Pets v3",
    }
    payload.update(overrides)
    return endpoints.PublishRequest(**payload)


def test_publish_defaults_to_every_offered_format():
    assert _request().formats == list(service.PUBLIC_FORMATS)
    assert _request().allow_downloads is True


def test_publish_rejects_an_unsupported_format():
    """The format name reaches a filename, so it is an allowlist."""
    with pytest.raises(ValueError):
        _request(formats=["parquet"])


def test_publish_rejects_a_path_traversal_as_a_format():
    with pytest.raises(ValueError):
        _request(formats=["../../etc/passwd"])


def test_publish_rejects_an_empty_title():
    with pytest.raises(ValueError):
        _request(title="")


def test_publish_caps_the_card_text():
    with pytest.raises(ValueError):
        _request(title="x" * 500)
    with pytest.raises(ValueError):
        _request(description="x" * 5000)


def test_an_empty_format_list_falls_back_to_the_default():
    """Publishing with downloads on but no formats would offer nothing."""
    assert _request(formats=[]).formats == list(service.PUBLIC_FORMATS)


def test_update_accepts_a_partial_edit():
    update = endpoints.PublicationUpdate(title="Renamed")
    assert update.title == "Renamed"
    assert update.description is None


# ── Counters ─────────────────────────────────────────────────────────────────


def test_only_known_counter_columns_can_be_incremented():
    """The column name is interpolated into SQL, so it is not caller-driven."""
    with pytest.raises(ValueError):
        endpoints._bump("slug", "title = 'x' --")
    with pytest.raises(ValueError):
        endpoints._bump("slug", "view_count; DROP TABLE users")


def test_revoked_rows_are_filtered_in_the_query():
    """Not loaded and then checked, so no path can forget the check."""
    source = inspect.getsource(endpoints._fetch_live_by_slug)
    assert "status = 'live'" in source


def test_revoking_discards_the_cached_archives():
    """A built zip left on disk keeps unpublished data downloadable."""
    source = inspect.getsource(endpoints.revoke_publication)
    assert "discard_archives" in source
    assert "allow_downloads = FALSE" in source
