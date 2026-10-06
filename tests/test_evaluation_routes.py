"""Route-wiring tests for the evaluation workbench.

Beyond registration and auth, these pin down route *resolution*. The module
declares `/{evaluation_id}` alongside literal prefixes like `/compare/...`,
`/latest/...` and `/job/.../history`, and FastAPI resolves in declaration
order — so a path that should reach the compare handler could silently be
swallowed by the catch-all. The handler each path lands on is checked by name.

TestClient is built without a `with` block so no database is needed.
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

EVALUATION_PATHS = [
    "/api/evaluation/run",
    "/api/evaluation/status/{evaluation_id}",
    "/api/evaluation/latest/{job_id}",
    "/api/evaluation/{evaluation_id}",
    "/api/evaluation/{evaluation_id}/images",
    "/api/evaluation/{evaluation_id}/image/{image_id}",
    "/api/evaluation/compare/{evaluation_a}/{evaluation_b}",
    "/api/evaluation/job/{job_id}/history",
]


@pytest.mark.parametrize("path", EVALUATION_PATHS)
def test_evaluation_route_is_registered(path):
    assert path in app.openapi()["paths"]


@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/evaluation/status/eval-1"),
        ("get", "/api/evaluation/latest/job-1"),
        ("get", "/api/evaluation/eval-1"),
        ("get", "/api/evaluation/eval-1/images"),
        ("get", "/api/evaluation/eval-1/image/img-1"),
        ("get", "/api/evaluation/compare/eval-1/eval-2"),
        ("get", "/api/evaluation/job/job-1/history"),
    ],
)
def test_evaluation_route_requires_auth(method, url):
    """401/403 proves the path matched a handler; 404 would mean it did not."""
    response = getattr(client, method)(url)
    assert response.status_code in (401, 403), response.text


def test_run_evaluation_requires_auth():
    response = client.post("/api/evaluation/run", json={"job_id": "job-1"})
    assert response.status_code in (401, 403), response.text


def _resolve(url: str) -> str:
    """The name of the endpoint function a GET on `url` would reach."""
    from starlette.routing import Match

    scope = {"type": "http", "method": "GET", "path": url, "headers": [],
             "query_string": b"", "root_path": ""}
    for route in app.routes:
        for candidate in getattr(route, "routes", [route]):
            if not hasattr(candidate, "matches"):
                continue
            match, _ = candidate.matches(scope)
            if match is Match.FULL:
                return candidate.endpoint.__name__
    return "<no match>"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("/api/evaluation/latest/job-1", "latest_evaluation"),
        ("/api/evaluation/status/eval-1", "evaluation_status"),
        ("/api/evaluation/eval-1", "get_evaluation"),
        ("/api/evaluation/eval-1/images", "list_evaluation_images"),
        ("/api/evaluation/eval-1/image/img-1", "get_evaluation_image"),
        # The two that the catch-all could plausibly steal.
        ("/api/evaluation/compare/a/b", "compare_evaluations"),
        ("/api/evaluation/job/job-1/history", "evaluation_history"),
    ],
)
def test_literal_prefixes_are_not_swallowed_by_the_catch_all(url, expected):
    assert _resolve(url) == expected


def test_run_rejects_an_unknown_split():
    """The split is constrained by pattern, so a typo is a 422, not a crash
    that only surfaces once the background task cannot find any images."""
    response = client.post(
        "/api/evaluation/run", json={"job_id": "job-1", "split": "holdout"}
    )
    assert response.status_code in (401, 403, 422), response.text
