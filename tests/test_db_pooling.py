"""Tests for the pooled DB layer: connection reuse, leak-safety, batched reads.

These use a fake connection so they need no MySQL. What they pin down is the
*number of connections checked out*, which is exactly what regressed before:
a per-dataset image fetch turned one list call into N+1 round trips.
"""

import json

import pytest

from app.db import session as db_session
from app.services import database as db


class FakeCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.dictionary = dictionary
        self._rows = []
        self.closed = False

    def execute(self, sql, params=None):
        self.conn.queries.append((" ".join(sql.split()), params))
        self._rows = self.conn.responder(sql, params)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, owner, responder):
        self.owner = owner
        self.responder = responder
        self.queries = []
        self.closed = False

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        self.owner.commits += 1

    def rollback(self):
        self.owner.rollbacks += 1

    def close(self):
        # Mirrors a pooled connection: close() returns it to the pool.
        self.closed = True
        self.owner.checked_in += 1


class FakePool:
    """Counts checkouts and check-ins so a leak shows up as an imbalance."""

    def __init__(self, responder):
        self.responder = responder
        self.checked_out = 0
        self.checked_in = 0
        self.commits = 0
        self.rollbacks = 0
        self.connections = []

    def hand_out(self):
        self.checked_out += 1
        conn = FakeConnection(self, self.responder)
        self.connections.append(conn)
        return conn

    @property
    def leaked(self):
        return self.checked_out - self.checked_in


@pytest.fixture
def pool(monkeypatch):
    """Install a fake pool behind get_db_connection for the duration of a test."""

    state = {"responder": lambda sql, params: []}
    fake = FakePool(lambda sql, params: state["responder"](sql, params))

    monkeypatch.setattr(db_session, "get_db_connection", fake.hand_out)
    fake.set_responder = lambda fn: state.__setitem__("responder", fn)
    return fake


def _dataset_row(ds_id, classes=("A", "B")):
    return {
        "id": ds_id,
        "user_id": 1,
        "name": f"ds-{ds_id}",
        "description": "",
        "classes": json.dumps(list(classes)),
        "total_images": 0,
        "annotated_images": 0,
        "created_at": None,
        "updated_at": None,
    }


def test_list_datasets_uses_two_connections_regardless_of_count(pool):
    """The old code took 1 + N connections; the batched version takes 2."""
    dataset_ids = [f"ds{i}" for i in range(25)]

    def responder(sql, params):
        if "FROM datasets" in sql:
            return [_dataset_row(i) for i in dataset_ids]
        if "FROM dataset_images" in sql:
            return [
                {
                    "dataset_id": ds_id,
                    "id": f"img-{ds_id}",
                    "filename": "a.jpg",
                    "original_name": "a.jpg",
                    "path": "p",
                    "annotated": True,
                    "split": "train",
                    "uploaded_at": None,
                    "status": "annotated",
                }
                for ds_id in dataset_ids
            ]
        return []

    pool.set_responder(responder)
    datasets = db.DatasetService.list_datasets()

    assert len(datasets) == 25
    assert pool.checked_out == 2, (
        f"expected 2 connections (datasets + batched images), got {pool.checked_out}"
    )
    assert pool.leaked == 0
    # Images are grouped back onto the right dataset.
    assert datasets[0]["images"][0]["id"] == f"img-{datasets[0]['id']}"
    # dataset_id is stripped from image rows, matching the old return shape.
    assert "dataset_id" not in datasets[0]["images"][0]


def test_images_are_fetched_in_a_single_in_query(pool):
    pool.set_responder(lambda sql, params: [])
    db.DatasetService.get_images_for_datasets(["a", "b", "c"])

    image_queries = [
        q for conn in pool.connections for q, _ in conn.queries if "dataset_images" in q
    ]
    assert len(image_queries) == 1
    assert "IN (%s,%s,%s)" in image_queries[0]


def test_malformed_classes_json_does_not_leak_a_connection(pool):
    """A bad `classes` value used to raise past `except Error` with the
    connection still checked out."""

    def responder(sql, params):
        if "FROM datasets" in sql:
            row = _dataset_row("ds1")
            row["classes"] = "{not valid json"
            return [row]
        return []

    pool.set_responder(responder)
    dataset = db.DatasetService.get_dataset("ds1")

    assert dataset is not None
    assert dataset["classes"] == []
    assert pool.leaked == 0


def test_db_cursor_returns_connection_when_body_raises(pool):
    pool.set_responder(lambda sql, params: [])

    with pytest.raises(ZeroDivisionError):
        with db_session.db_cursor() as cursor:
            cursor.execute("SELECT 1")
            1 / 0

    assert pool.leaked == 0


def test_db_cursor_rolls_back_a_failed_write(pool):
    pool.set_responder(lambda sql, params: [])

    with pytest.raises(ValueError):
        with db_session.db_cursor(commit=True) as cursor:
            cursor.execute("UPDATE datasets SET name = %s", ("x",))
            raise ValueError("boom")

    assert pool.rollbacks == 1
    assert pool.commits == 0
    assert pool.leaked == 0


def test_db_cursor_commits_on_success(pool):
    pool.set_responder(lambda sql, params: [])

    with db_session.db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE datasets SET name = %s", ("x",))

    assert pool.commits == 1
    assert pool.leaked == 0


def test_db_cursor_raises_when_database_unavailable(monkeypatch):
    monkeypatch.setattr(db_session, "get_db_connection", lambda: None)
    with pytest.raises(RuntimeError, match="Database connection unavailable"):
        with db_session.db_cursor():
            pass
