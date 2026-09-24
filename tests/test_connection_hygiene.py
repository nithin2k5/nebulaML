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

# Functions that still open a connection by hand without a finally. Each one is
# a latent pool leak. Delete entries as they are converted to db_cursor(); the
# test fails if anything not listed here appears.
_KNOWN_LEAKS = {
    ("api/v1/endpoints/annotations.py", "split_dataset"),
    ("api/v1/endpoints/annotations.py", "propagate_annotations_to_all"),
    ("api/v1/endpoints/auth.py", "register"),
    ("api/v1/endpoints/auth.py", "login"),
    ("api/v1/endpoints/auth.py", "update_profile"),
    ("api/v1/endpoints/auth.py", "request_change_email_current"),
    ("api/v1/endpoints/auth.py", "verify_change_email_current"),
    ("api/v1/endpoints/auth.py", "verify_change_email_new"),
    ("api/v1/endpoints/auth.py", "get_my_stats"),
    ("api/v1/endpoints/auth.py", "list_users"),
    ("api/v1/endpoints/auth.py", "get_user_by_username"),
    ("api/v1/endpoints/auth.py", "update_user_role"),
    ("api/v1/endpoints/auth.py", "delete_user"),
    ("db/session.py", "create_tables"),
    ("db/session.py", "check_db_connection"),
    ("services/database.py", "create_dataset"),
    ("services/database.py", "update_dataset"),
    ("services/database.py", "delete_dataset"),
    ("services/database.py", "add_image"),
    ("services/database.py", "delete_image"),
    ("services/database.py", "get_unannotated_images"),
    ("services/database.py", "update_image_split"),
    ("services/database.py", "mark_image_annotated"),
    ("services/database.py", "save_annotation"),
    ("services/database.py", "get_annotation"),
    ("services/database.py", "get_all_dataset_annotations"),
    ("services/database.py", "get_dataset_stats"),
    ("services/database.py", "create_version"),
    ("services/database.py", "add_version_image"),
    ("services/database.py", "get_version"),
    ("services/database.py", "list_dataset_versions"),
    ("services/database.py", "upsert_job"),
    ("services/database.py", "load_all_jobs"),
    ("services/database.py", "save_snapshot"),
    ("services/database.py", "get_history"),
    ("services/database.py", "get_latest_snapshot"),
    ("services/database.py", "get_config"),
    ("services/database.py", "upsert_config"),
    ("services/database.py", "increment_annotation_count"),
    ("services/database.py", "reset_annotation_count"),
    ("services/database.py", "create_api_key"),
    ("services/database.py", "get_user_api_keys"),
    ("services/database.py", "get_api_key_by_hash"),
    ("services/database.py", "delete_api_key"),
}


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


@pytest.mark.parametrize("path, name", sorted(_KNOWN_LEAKS))
def test_known_leaks_are_tracked(path, name):
    """Documents the remaining debt so it stays visible in the test report."""
    assert (APP_ROOT / path).exists()


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
