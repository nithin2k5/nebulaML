"""Route-wiring tests for the semantic search endpoints.

Same approach as test_uncertainty_route: assert the routes exist and are
guarded, checked against the OpenAPI schema so the assertions do not depend on
how FastAPI stores included routers. TestClient is built without a `with`
block so the lifespan handler — and therefore the database — is never needed.
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

SEARCH_PATHS = [
    "/api/search/index/{dataset_id}",
    "/api/search/index-status/{job_id}",
    "/api/search/status/{dataset_id}",
    "/api/search/text",
    "/api/search/similar",
    "/api/search/duplicates/{dataset_id}",
    "/api/search/clusters/{dataset_id}",
]


@pytest.mark.parametrize("path", SEARCH_PATHS)
def test_search_route_is_registered(path):
    assert path in app.openapi()["paths"]


@pytest.mark.parametrize(
    "method,url",
    [
        ("post", "/api/search/index/fake-id"),
        ("get", "/api/search/status/fake-id"),
        ("get", "/api/search/duplicates/fake-id"),
        ("get", "/api/search/clusters/fake-id"),
    ],
)
def test_search_route_requires_auth(method, url):
    """A 401/403 proves the path matched a handler; 404 would mean it did not."""
    response = getattr(client, method)(url)
    assert response.status_code in (401, 403), response.text


@pytest.mark.parametrize(
    "url,payload",
    [
        ("/api/search/text", {"dataset_id": "fake-id", "query": "a red truck"}),
        ("/api/search/similar", {"dataset_id": "fake-id", "image_id": "img-1"}),
    ],
)
def test_search_post_routes_require_auth(url, payload):
    response = client.post(url, json=payload)
    assert response.status_code in (401, 403), response.text


def test_text_search_rejects_an_empty_query_before_touching_the_model():
    """Validation must run on the request body, not after a CLIP load."""
    response = client.post(
        "/api/search/text", json={"dataset_id": "fake-id", "query": ""}
    )
    # Unauthenticated, so auth may reject first; what matters is that it is
    # never a 404 (missing route) or a 500 (validation reached the model).
    assert response.status_code in (401, 403, 422), response.text
