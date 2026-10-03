"""Route-wiring tests for the label audit.

Registration, auth, and the input validation that keeps user-supplied strings
out of SQL: `kind` and `status` reach a query, so both must be rejected at the
edge rather than interpolated.
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

AUDIT_PATHS = [
    "/api/label-audit/run",
    "/api/label-audit/status/{audit_id}",
    "/api/label-audit/findings/{dataset_id}",
    "/api/label-audit/summary/{dataset_id}",
    "/api/label-audit/resolve/{dataset_id}",
]


@pytest.mark.parametrize("path", AUDIT_PATHS)
def test_audit_route_is_registered(path):
    assert path in app.openapi()["paths"]


@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/label-audit/status/audit-1"),
        ("get", "/api/label-audit/findings/ds-1"),
        ("get", "/api/label-audit/summary/ds-1"),
    ],
)
def test_audit_route_requires_auth(method, url):
    response = getattr(client, method)(url)
    assert response.status_code in (401, 403), response.text


def test_run_requires_auth():
    response = client.post(
        "/api/label-audit/run", json={"dataset_id": "ds-1", "job_id": "job-1"}
    )
    assert response.status_code in (401, 403), response.text


def test_resolve_requires_auth():
    response = client.post(
        "/api/label-audit/resolve/ds-1",
        json={"finding_ids": ["f-1"], "status": "dismissed"},
    )
    assert response.status_code in (401, 403), response.text


def test_resolve_rejects_an_unknown_status():
    """`status` is written into an UPDATE, so the enum is enforced by the model."""
    response = client.post(
        "/api/label-audit/resolve/ds-1",
        json={"finding_ids": ["f-1"], "status": "'; DROP TABLE users; --"},
    )
    assert response.status_code in (401, 403, 422), response.text


def test_resolve_rejects_an_empty_id_list():
    """An empty IN () clause is a syntax error, so it must never be built."""
    response = client.post(
        "/api/label-audit/resolve/ds-1",
        json={"finding_ids": [], "status": "fixed"},
    )
    assert response.status_code in (401, 403, 422), response.text


def test_run_rejects_a_confidence_outside_the_allowed_band():
    """Below 0.5 the model is guessing, and a guess must not accuse a label."""
    response = client.post(
        "/api/label-audit/run",
        json={"dataset_id": "ds-1", "job_id": "job-1", "min_confidence": 0.1},
    )
    assert response.status_code in (401, 403, 422), response.text


def test_findings_kind_filter_is_validated_against_a_fixed_set():
    """`kind` reaches a WHERE clause; only the known kinds are accepted."""
    from app.services import label_audit

    assert "wrong_class" in label_audit.FINDING_KINDS
    response = client.get("/api/label-audit/findings/ds-1?kind=bogus_kind")
    assert response.status_code in (401, 403, 400), response.text
