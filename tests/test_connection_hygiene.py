"""Static guard against leaking pooled MySQL connections.

get_db_connection() checks a connection out of a fixed-size pool and the caller
must return it. A handler that closes only on the success path loses the
connection whenever the body raises; enough of those and the pool is exhausted
and the API stops serving. db_cursor() exists precisely so the close happens in
a finally.

This walks the AST rather than running anything, so it needs no live MySQL. It
is a ratchet: _KNOWN_LEAKS may shrink but must never grow.
"""

import ast
import pathlib

import pytest

APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / "server" / "app"

# Every function that checks a connection out of the pool now returns it in a
# finally (or goes through db_cursor). The list is empty and must stay that
# way: a new entry here means a new way to exhaust the pool.
_KNOWN_LEAKS: set = set()


def _closes_in_finally(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Attribute) and sub.attr == "close":
                        return True
    return False


def _uses_context_manager(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "db_cursor":
                    return True
    return False


def _leaking_functions():
    leaks = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text())
        rel = path.relative_to(APP_ROOT).as_posix()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls_get = any(
                isinstance(n, ast.Call) and getattr(n.func, "id", None) == "get_db_connection"
                for n in ast.walk(fn)
            )
            if not calls_get:
                continue
            if _closes_in_finally(fn) or _uses_context_manager(fn):
                continue
            leaks.add((rel, fn.name))
    return leaks


def test_no_new_connection_leaks():
    """A handler that closes only on the success path loses a pooled connection."""
    new = _leaking_functions() - _KNOWN_LEAKS
    assert not new, (
        "these open a pooled connection without closing it in a finally:\n  "
        + "\n  ".join(f"{path}::{name}" for path, name in sorted(new))
        + "\nUse `with db_cursor(...)` instead of get_db_connection()."
    )


def test_known_leak_list_has_no_stale_entries():
    """Keeps the ratchet honest: fixing a leak must also shrink the list."""
    stale = _KNOWN_LEAKS - _leaking_functions()
    assert not stale, (
        "these no longer leak — remove them from _KNOWN_LEAKS:\n  "
        + "\n  ".join(f"{path}::{name}" for path, name in sorted(stale))
    )


def test_get_current_user_does_not_leak():
    """It runs on every authenticated request; a leak here drains the pool fastest."""
    assert ("api/v1/endpoints/auth.py", "get_current_user") not in _leaking_functions()


def test_every_pool_caller_is_accounted_for():
    """Sanity-check the detector itself: it must still see the call sites."""
    callers = 0
    for path in APP_ROOT.rglob("*.py"):
        callers += path.read_text().count("get_db_connection()")
    assert callers > 20, "detector found almost no call sites — has it broken?"


# ── Runtime proof ────────────────────────────────────────────────────────────

def test_db_cursor_returns_the_connection_when_the_body_raises():
    """The property the whole ratchet is about, exercised rather than inferred."""
    from unittest.mock import MagicMock, patch

    from app.db import session as db_session

    connection = MagicMock()
    with patch.object(db_session, "get_db_connection", return_value=connection):
        with pytest.raises(ValueError):
            with db_session.db_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT 1")
                raise ValueError("something in the handler blew up")

    connection.close.assert_called_once()


def test_db_cursor_rolls_back_a_failed_write():
    from unittest.mock import MagicMock, patch

    from app.db import session as db_session

    connection = MagicMock()
    with patch.object(db_session, "get_db_connection", return_value=connection):
        with pytest.raises(ValueError):
            with db_session.db_cursor(commit=True) as cursor:
                cursor.execute("INSERT INTO t VALUES (1)")
                raise ValueError("boom")

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()
