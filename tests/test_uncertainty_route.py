"""Route-wiring tests for the active-learning uncertainty endpoint.

These assert the route is registered and guarded — not that it returns data.
TestClient is constructed without a `with` block on purpose: that skips the
lifespan handler, so the tests do not need a live database to start the app.

Registration is checked against the OpenAPI schema rather than `app.routes`.
FastAPI 0.141+ keeps included routers as `_IncludedRouter` entries instead of
flattening them, so walking `app.routes` for paths is version-fragile.
"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app, raise_server_exceptions=False)

UNCERTAINTY_PATH = "/api/annotations/datasets/{dataset_id}/uncertainty"


def test_uncertainty_endpoint_is_registered():
    assert UNCERTAINTY_PATH in app.openapi()["paths"]


def test_uncertainty_endpoint_requires_auth():
    """Unauthenticated calls are rejected by the auth dependency, not by routing.

    A 401/403 proves the path matched a handler; a 404 would mean it did not.
    """
    response = client.get("/api/annotations/datasets/fake-id/uncertainty")
    assert response.status_code in (401, 403), response.text
