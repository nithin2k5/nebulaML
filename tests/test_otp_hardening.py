"""Tests for one-time-code generation and brute-force resistance.

Sign-in is passwordless, so /verify is the front door: these cover the code's
randomness, its constant-time comparison, and the per-code attempt budget that
bounds an attacker who has more IPs than the rate limiter can key on.
"""

from unittest.mock import MagicMock

import pytest

from app.api.v1.endpoints import auth


# ── Code generation ──────────────────────────────────────────────────────────

def test_otp_is_always_six_digits():
    for _ in range(500):
        code = auth._generate_otp()
        assert len(code) == 6
        assert code.isdigit()
        assert not code.startswith("0")


def test_otp_uses_the_csprng_not_the_mersenne_twister(monkeypatch):
    """`random` is seedable and its state is recoverable from observed output;
    seeding it must not make the next code predictable."""
    import random

    random.seed(1234)
    first = auth._generate_otp()
    random.seed(1234)
    second = auth._generate_otp()
    assert first != second, "OTP tracks random.seed() — it is not using secrets"


def test_otp_space_is_actually_explored():
    """A constant or badly bounded generator would collapse this set."""
    codes = {auth._generate_otp() for _ in range(2000)}
    assert len(codes) > 1500


# ── Comparison ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "stored, supplied, expected",
    [
        ("123456", "123456", True),
        ("123456", "123457", False),
        ("123456", "", False),
        (None, "123456", False),
        ("", "123456", False),
        (123456, "123456", True),  # MySQL may hand back a non-str
    ],
)
def test_otp_matches(stored, supplied, expected):
    assert auth._otp_matches(stored, supplied) is expected


# ── Attempt budget ───────────────────────────────────────────────────────────

def _fake_db():
    connection, cursor = MagicMock(), MagicMock()
    return connection, cursor


def test_failed_attempt_increments_below_the_budget():
    connection, cursor = _fake_db()
    auth._register_failed_attempt(
        connection, cursor, "users", {"id": 7, "verification_attempts": 1}
    )
    sql, params = cursor.execute.call_args[0]
    assert "verification_attempts = %s" in sql
    assert params == (2, 7)
    connection.commit.assert_called_once()


def test_code_is_burned_once_the_budget_is_spent():
    connection, cursor = _fake_db()
    auth._register_failed_attempt(
        connection,
        cursor,
        "users",
        {"id": 7, "verification_attempts": auth.MAX_OTP_ATTEMPTS - 1},
    )
    sql, params = cursor.execute.call_args[0]
    assert "verification_code = NULL" in sql
    assert "verification_attempts = 0" in sql
    assert params == (7,)


def test_missing_attempt_column_is_treated_as_zero():
    """Rows read before the migration ran carry no counter."""
    connection, cursor = _fake_db()
    auth._register_failed_attempt(connection, cursor, "users", {"id": 7})
    _, params = cursor.execute.call_args[0]
    assert params == (1, 7)


def test_table_name_is_allowlisted():
    """The table is interpolated, so it must never accept caller-supplied text."""
    connection, cursor = _fake_db()
    with pytest.raises(ValueError):
        auth._register_failed_attempt(
            connection, cursor, "users; DROP TABLE users", {"id": 1}
        )
    cursor.execute.assert_not_called()


def test_bookkeeping_failure_does_not_mask_the_rejection():
    """A dead connection while counting must not turn a 400 into a 500."""
    import mysql.connector

    connection, cursor = _fake_db()
    cursor.execute.side_effect = mysql.connector.Error("gone away")
    auth._register_failed_attempt(connection, cursor, "users", {"id": 7})


# ── Rate limiting ────────────────────────────────────────────────────────────

def _declared_limits(func_name: str):
    """slowapi keys its registry on '<module>.<function>'."""
    key = f"{auth.__name__}.{func_name}"
    return auth.limiter._route_limits.get(key, [])


def test_verify_is_rate_limited():
    """/verify mints sessions; it must not fall back to the global 200/minute."""
    limits = _declared_limits("verify_otp")
    assert limits, "/verify carries no rate limit of its own"
    assert any("5 per 1 minute" in str(limit.limit) for limit in limits)


@pytest.mark.parametrize(
    "endpoint", ["login", "register", "resend_otp", "verify_otp", "refresh_tokens"]
)
def test_every_credential_endpoint_is_rate_limited(endpoint):
    """Each of these either mints a session or sends a code to an inbox."""
    assert _declared_limits(endpoint), f"/{endpoint} carries no rate limit"
