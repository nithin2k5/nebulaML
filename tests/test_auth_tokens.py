"""Tests for token typing, lifetimes, refresh rotation and security headers."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core import rbac
from app.services.refresh_tokens import RefreshTokenService
from main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Token typing ─────────────────────────────────────────────────────────────

def test_access_token_carries_its_type():
    token = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    payload = jwt.decode(token, rbac.SECRET_KEY, algorithms=[rbac.ALGORITHM])
    assert payload[rbac.TOKEN_TYPE_CLAIM] == rbac.TOKEN_TYPE_ACCESS


def test_refresh_token_is_not_accepted_as_an_access_token():
    """Both are signed with the same secret; only the type claim separates them."""
    refresh = rbac.create_refresh_token(user_id=1, jti="abc")
    assert rbac.decode_refresh_token(refresh) is not None
    assert rbac.decode_access_token(refresh) is None


def test_access_token_is_not_accepted_as_a_refresh_token():
    access = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    assert rbac.decode_access_token(access) is not None
    assert rbac.decode_refresh_token(access) is None


def test_invite_style_token_is_rejected_as_an_access_token():
    """collaboration.py signs invites with the same key and algorithm."""
    invite = jwt.encode(
        {"dataset_id": "d1", "email": "a@b.c", "role": "annotator", "typ": "invite"},
        rbac.SECRET_KEY,
        algorithm=rbac.ALGORITHM,
    )
    assert rbac.decode_access_token(invite) is None


def test_legacy_token_without_a_type_still_authenticates():
    """Tokens minted before the claim existed must not sign everyone out."""
    legacy = jwt.encode(
        {"user_id": 1, "username": "u", "role": "user"},
        rbac.SECRET_KEY,
        algorithm=rbac.ALGORITHM,
    )
    assert rbac.decode_access_token(legacy) is not None
    # ...but a legacy token is still not usable as a refresh token.
    assert rbac.decode_refresh_token(legacy) is None


def test_expired_token_is_rejected():
    expired = rbac.create_access_token({"user_id": 1}, expires_delta=timedelta(seconds=-1))
    assert rbac.decode_access_token(expired) is None


def test_tampered_token_is_rejected():
    token = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    forged = jwt.encode(
        {"user_id": 999, "typ": "access"}, "not-the-real-secret", algorithm=rbac.ALGORITHM
    )
    assert rbac.decode_access_token(token) is not None
    assert rbac.decode_access_token(forged) is None


def test_access_token_lifetime_is_not_a_week():
    """The default was 10080 minutes; a stolen token was good for seven days."""
    assert rbac.ACCESS_TOKEN_EXPIRE_MINUTES <= 24 * 60


# ── Refresh rotation ─────────────────────────────────────────────────────────

def _utcnow():
    """Naive UTC, matching what the service compares expires_at against."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeStore:
    """In-memory stand-in for the refresh_tokens table."""

    def __init__(self):
        self.rows = {}
        self.counter = 0

    def issue(self, user_id, ttl_days):
        self.counter += 1
        jti = f"jti-{self.counter}"
        self.rows[jti] = {
            "jti": jti,
            "user_id": user_id,
            "expires_at": _utcnow() + timedelta(days=ttl_days),
            "revoked_at": None,
        }
        return jti

    def get(self, jti):
        return self.rows.get(jti)

    def revoke(self, jti):
        if jti in self.rows and self.rows[jti]["revoked_at"] is None:
            self.rows[jti]["revoked_at"] = _utcnow()

    def revoke_all_for_user(self, user_id):
        n = 0
        for row in self.rows.values():
            if row["user_id"] == user_id and row["revoked_at"] is None:
                row["revoked_at"] = _utcnow()
                n += 1
        return n


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(RefreshTokenService, "issue", staticmethod(fake.issue))
    monkeypatch.setattr(RefreshTokenService, "get", staticmethod(fake.get))
    monkeypatch.setattr(RefreshTokenService, "revoke", staticmethod(fake.revoke))
    monkeypatch.setattr(
        RefreshTokenService, "revoke_all_for_user", staticmethod(fake.revoke_all_for_user)
    )
    return fake


def test_rotate_consumes_the_old_token_and_issues_a_new_one(store):
    jti = store.issue(user_id=7, ttl_days=7)
    new_jti = RefreshTokenService.rotate(jti, user_id=7, ttl_days=7)

    assert new_jti is not None and new_jti != jti
    assert store.rows[jti]["revoked_at"] is not None, "old token should be consumed"
    assert store.rows[new_jti]["revoked_at"] is None


def test_reusing_a_rotated_token_revokes_the_whole_family(store):
    """Theft detection: a replayed refresh token invalidates every session."""
    first = store.issue(user_id=7, ttl_days=7)
    second = RefreshTokenService.rotate(first, user_id=7, ttl_days=7)

    # An attacker replays the token that was already rotated.
    assert RefreshTokenService.rotate(first, user_id=7, ttl_days=7) is None
    # The legitimate client's current token is taken down too — the server
    # cannot tell which party is which, so it forces a fresh sign-in.
    assert store.rows[second]["revoked_at"] is not None


def test_rotate_rejects_a_jti_belonging_to_another_user(store):
    jti = store.issue(user_id=7, ttl_days=7)
    assert RefreshTokenService.rotate(jti, user_id=8, ttl_days=7) is None


def test_rotate_rejects_an_unknown_jti(store):
    assert RefreshTokenService.rotate("never-issued", user_id=7, ttl_days=7) is None


def test_rotate_rejects_an_expired_row(store):
    jti = store.issue(user_id=7, ttl_days=7)
    store.rows[jti]["expires_at"] -= timedelta(days=14)
    assert RefreshTokenService.rotate(jti, user_id=7, ttl_days=7) is None


# ── Endpoints and headers ────────────────────────────────────────────────────

def test_refresh_endpoint_rejects_a_garbage_token():
    response = client.post("/api/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert response.status_code == 401


def test_refresh_endpoint_rejects_an_access_token():
    access = rbac.create_access_token({"user_id": 1, "username": "u", "role": "user"})
    response = client.post("/api/auth/refresh", json={"refresh_token": access})
    assert response.status_code == 401


def test_security_headers_are_present_on_api_responses():
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_docs_get_a_policy_that_allows_swaggers_bundle():
    response = client.get("/docs")
    csp = response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp


def test_hsts_is_off_by_default():
    """Sending HSTS over plain http://localhost pins the browser to https."""
    response = client.get("/health")
    assert "strict-transport-security" not in response.headers
