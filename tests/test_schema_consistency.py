"""Guards on the hand-rolled schema in app/db/session.py.

Tables are declared with CREATE TABLE IF NOT EXISTS, which means a second
declaration of the same table is not an error — it is silently ignored. That
is how auto_retrain_configs shipped with the wrong columns: it was declared
twice, the first one won, and every reader queried columns that did not exist.
These tests read the DDL as text so they need no live MySQL.
"""

import inspect
import re

import pytest

from app.db import session as db_session

_CREATE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\s*\)", re.DOTALL | re.IGNORECASE
)


def _declared_tables():
    """Map table name -> list of column-name sets, one per declaration."""
    src = inspect.getsource(db_session.create_tables)
    found = {}
    for name, body in _CREATE_RE.findall(src):
        columns = set()
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            first = line.split()[0].upper()
            if first in {
                "PRIMARY", "FOREIGN", "INDEX", "UNIQUE", "KEY", "CONSTRAINT", "CHECK",
            }:
                continue
            columns.add(line.split()[0].lower())
        found.setdefault(name.lower(), []).append(columns)
    return found


def test_no_table_is_declared_twice():
    """IF NOT EXISTS makes a duplicate declaration silent, so assert on it."""
    duplicates = {
        name: len(decls) for name, decls in _declared_tables().items() if len(decls) > 1
    }
    assert not duplicates, (
        f"declared more than once in create_tables(): {duplicates}. "
        "The first declaration wins and the rest are silently ignored."
    )


def test_schema_is_not_empty():
    """Guard the regex itself — a parse failure must not vacuously pass."""
    tables = _declared_tables()
    assert len(tables) > 10
    assert "users" in tables
    assert "datasets" in tables


# Columns each service reads or writes, checked against the declared DDL.
# Keyed by table, so a schema edit that drops a column fails here rather than
# at runtime with "Unknown column".
_REQUIRED_COLUMNS = {
    "auto_retrain_configs": {
        "dataset_id",
        "enabled",
        "min_new_annotations",
        "annotations_since_last_train",
        "last_triggered_at",
    },
    "users": {
        "id", "username", "email", "role", "is_verified",
        "verification_code", "verification_code_expires", "verification_attempts",
    },
    "pending_registrations": {
        "id", "username", "email", "role",
        "verification_code", "verification_code_expires", "verification_attempts",
    },
    "refresh_tokens": {"jti", "user_id", "expires_at", "revoked_at"},
}


@pytest.mark.parametrize("table, required", sorted(_REQUIRED_COLUMNS.items()))
def test_declared_columns_cover_what_the_code_reads(table, required):
    declarations = _declared_tables().get(table)
    assert declarations, f"{table} is not declared in create_tables()"
    declared = declarations[0]
    missing = required - declared
    assert not missing, f"{table} is missing columns the code queries: {sorted(missing)}"
