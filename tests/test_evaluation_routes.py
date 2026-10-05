"""Route-wiring and contract tests for the evaluation endpoints.

TestClient is built without a `with` block on purpose, following
test_uncertainty_route: that skips the lifespan handler, so these run without
a live database.

Beyond registration, these pin two things that silently rot otherwise — the
request validation, and the agreement between the error vocabulary the service
emits, the one the API accepts as a filter, and the one the ENUM column stores.
"""

import inspect
import re

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.evaluation import (
    _VALID_ERROR_TYPES,
    _VALID_SPLITS,
    _decode_json_columns,
    EvaluateRequest,
)
from app.db import session as db_session
from main import app

client = TestClient(app, raise_server_exceptions=False)

PATHS = [
    "/api/evaluation/run",
    "/api/evaluation/runs/{dataset_id}",
    "/api/evaluation/run/{run_id}",
    "/api/evaluation/run/{run_id}/errors",
    "/api/evaluation/run/{run_id}/threshold-sweep",
    "/api/evaluation/run/{run_id}/image/{filename}",
    "/api/evaluation/compare",
    "/api/evaluation/image/{run_id}/{filename}",
]


# ── Wiring ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", PATHS)
def test_route_is_registered(path):
    assert path in app.openapi()["paths"]


def test_delete_run_is_registered():
    assert "delete" in app.openapi()["paths"]["/api/evaluation/run/{run_id}"]


@pytest.mark.parametrize(
    "method, url",
    [
        ("post", "/api/evaluation/run"),
        ("get", "/api/evaluation/runs/fake-dataset"),
        ("get", "/api/evaluation/run/fake-run"),
        ("get", "/api/evaluation/run/fake-run/errors"),
        ("get", "/api/evaluation/run/fake-run/threshold-sweep"),
        ("get", "/api/evaluation/run/fake-run/image/x.jpg"),
        ("get", "/api/evaluation/compare?runs=a,b"),
        ("get", "/api/evaluation/image/fake-run/x.jpg"),
        ("delete", "/api/evaluation/run/fake-run"),
    ],
)
def test_route_requires_auth(method, url):
    """A 401/403 proves the path reached a guarded handler; 404 would not.

    422 is also accepted for the POST, whose body is validated before the
    dependency runs — either way nothing unauthenticated gets through.
    """
    response = getattr(client, method)(url)
    assert response.status_code in (401, 403, 422), response.text


def test_image_route_rejects_a_bad_query_token():
    """The <img src> path must not become an unauthenticated read."""
    response = client.get("/api/evaluation/image/fake-run/x.jpg?token=not-a-real-token")
    assert response.status_code == 401, response.text


# ── Request validation ───────────────────────────────────────────────────────


def _request(**overrides):
    payload = {
        "dataset_id": "d1",
        "version_id": "v1",
        "job_id": "j1",
    }
    payload.update(overrides)
    return EvaluateRequest(**payload)


def test_evaluate_request_defaults_to_the_test_split():
    """The held-out split is the point of the feature, so it is the default."""
    assert _request().split == "test"
    assert _request().conf_threshold == 0.25
    assert _request().iou_threshold == 0.5


@pytest.mark.parametrize("split", _VALID_SPLITS)
def test_evaluate_request_accepts_every_real_split(split):
    assert _request(split=split).split == split


def test_evaluate_request_rejects_an_unknown_split():
    """An unchecked value would reach the ENUM column and fail as a 500."""
    with pytest.raises(ValueError):
        _request(split="holdout")


@pytest.mark.parametrize("conf", [-0.1, 1.5])
def test_evaluate_request_rejects_out_of_range_confidence(conf):
    with pytest.raises(ValueError):
        _request(conf_threshold=conf)


def test_evaluate_request_rejects_a_zero_iou_threshold():
    """IoU 0 would make every box match everything it touches."""
    with pytest.raises(ValueError):
        _request(iou_threshold=0.0)


# ── JSON column decoding ─────────────────────────────────────────────────────


def test_decode_json_columns_parses_strings():
    row = {"metrics": '{"map50": 0.5}', "class_names": '["cat"]'}
    decoded = _decode_json_columns(row)
    assert decoded["metrics"] == {"map50": 0.5}
    assert decoded["class_names"] == ["cat"]


def test_decode_json_columns_leaves_decoded_objects_alone():
    """mysql-connector hands back objects on some versions, strings on others."""
    row = {"metrics": {"map50": 0.5}, "confusion_matrix": None}
    decoded = _decode_json_columns(row)
    assert decoded["metrics"] == {"map50": 0.5}
    assert decoded["confusion_matrix"] is None


def test_decode_json_columns_survives_malformed_json():
    """A corrupt row should degrade to None, not 500 the whole results page."""
    assert _decode_json_columns({"metrics": "{not json"})["metrics"] is None


# ── Vocabulary agreement ─────────────────────────────────────────────────────


def _enum_values(table: str, column: str):
    """Read an ENUM's values straight out of the CREATE TABLE text."""
    src = inspect.getsource(db_session.create_tables)
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table} \((?:.|\n)*?\n\s*\)", src
    )
    assert match, f"{table} is not declared in create_tables()"
    column_match = re.search(rf"{column} ENUM\(([^)]*)\)", match.group(0))
    assert column_match, f"{table}.{column} is not an ENUM"
    return {value.strip().strip("'") for value in column_match.group(1).split(",")}


def test_api_error_filter_matches_the_stored_enum():
    """A filter value the column cannot hold would 500 instead of 400."""
    assert set(_VALID_ERROR_TYPES) == _enum_values("evaluation_predictions", "error_type")


def test_api_splits_match_the_stored_enum():
    assert set(_VALID_SPLITS) == _enum_values("evaluation_runs", "split")


def _emitted_literals(field: str) -> set:
    """Collect the values the service assigns to one record field.

    Both spellings are matched — the dict literal `"outcome": "tp"` and the
    assignment `record["outcome"] = "fp"` — plus the bare returns of
    `_diagnose_false_positive`. Missing a spelling would make this test pass
    vacuously, which is what the non-empty assertions below guard.
    """
    from app.services import evaluation as service

    src = inspect.getsource(service)
    found = set(re.findall(rf'"{field}": "(\w+)"', src))
    found |= set(re.findall(rf'\["{field}"\] = "(\w+)"', src))
    return found


def test_service_emits_only_error_types_the_column_accepts():
    """The service, the API filter and the column must share one vocabulary."""
    from app.services import evaluation as service

    emitted = _emitted_literals("error_type")
    # `_diagnose_false_positive` returns its verdict rather than assigning it.
    emitted |= set(re.findall(r'return "(\w+)", ', inspect.getsource(service)))
    assert emitted, "found no error_type literals — the regex needs updating"
    assert emitted == _enum_values("evaluation_predictions", "error_type")


def test_service_emits_only_outcomes_the_column_accepts():
    emitted = _emitted_literals("outcome")
    assert emitted, "found no outcome literals — the regex needs updating"
    assert emitted == _enum_values("evaluation_predictions", "outcome")
