"""Auth and caching behaviour of the image endpoint.

Images are per-user authorised content served to <img src>, which is an awkward
combination: the tag cannot send an Authorization header, so the endpoint also
accepts ?token=. That makes the caching and referrer headers part of the
security surface, not just performance tuning.
"""

import inspect

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import annotations
from app.core import rbac
from main import app

client = TestClient(app, raise_server_exceptions=False)

IMAGE_URL = "/api/annotations/image/some-dataset/photo.jpg"


def test_unauthenticated_request_is_rejected():
    assert client.get(IMAGE_URL).status_code == 401


def test_garbage_token_is_rejected():
    assert client.get(f"{IMAGE_URL}?token=not-a-jwt").status_code == 401
    assert client.get(
        IMAGE_URL, headers={"Authorization": "Bearer not-a-jwt"}
    ).status_code == 401


def test_refresh_token_is_not_accepted_here():
    """serve_image calls decode_access_token, which rejects other token types."""
    refresh = rbac.create_refresh_token(user_id=1, jti="abc")
    assert client.get(f"{IMAGE_URL}?token={refresh}").status_code == 401
    assert client.get(
        IMAGE_URL, headers={"Authorization": f"Bearer {refresh}"}
    ).status_code == 401


def test_bearer_header_is_actually_read():
    """The docstring promised header auth while only ?token= was implemented.

    A valid access token must get *past* authentication — it then fails on the
    dataset lookup (404/500 without a database), which is the point: 401 would
    mean the header was ignored.
    """
    token = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    response = client.get(IMAGE_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code != 401


def test_bearer_scheme_is_matched_case_insensitively():
    token = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    assert client.get(
        IMAGE_URL, headers={"Authorization": f"bearer {token}"}
    ).status_code != 401


def test_malformed_authorization_header_falls_through_to_the_query_token():
    token = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    response = client.get(
        f"{IMAGE_URL}?token={token}", headers={"Authorization": "Basic abc123"}
    )
    assert response.status_code != 401


# ── Response headers ─────────────────────────────────────────────────────────

def test_authorised_images_are_not_publicly_cacheable():
    """`public` would let a shared cache serve one user's image to another."""
    source = inspect.getsource(annotations.serve_image)
    assert '"Cache-Control": "private' in source
    assert "public, max-age" not in source


def test_image_responses_suppress_the_referrer():
    """?token= is a credential in a URL; Referer must not carry it off-site."""
    source = inspect.getsource(annotations.serve_image)
    assert '"Referrer-Policy": "no-referrer"' in source


# ── Path traversal ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "filename", ["../../../etc/passwd", "..%2f..%2fetc%2fpasswd", "sub/dir.jpg", ".."]
)
def test_traversal_attempts_never_reach_the_filesystem(filename):
    token = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    response = client.get(
        f"/api/annotations/image/some-dataset/{filename}?token={token}"
    )
    assert response.status_code in (400, 404, 500)
    assert b"root:" not in response.content
