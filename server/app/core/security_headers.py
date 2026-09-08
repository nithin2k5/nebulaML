"""Security response headers, including the Content-Security-Policy.

The access token lives in localStorage, which any script running on the page
can read. Shortening the token's life limits how long a stolen one is useful;
CSP attacks the other half of the problem by making it hard to get a script
running on the page at all.

The API serves JSON and a Swagger UI, not the app itself — the strict policy
below applies to API responses, and /docs and /redoc get a relaxed one because
Swagger's bundle needs inline styles and its CDN. The frontend sends its own
headers from next.config.mjs.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# JSON endpoints load nothing at all, so everything is denied by default.
_API_CSP = "; ".join(
    [
        "default-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ]
)

# Swagger UI and ReDoc pull their bundles from jsdelivr and set inline styles.
_DOCS_CSP = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "script-src 'self' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "worker-src 'self' blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
    ]
)

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, hsts: bool = False):
        super().__init__(app)
        # HSTS is only meaningful over TLS, and setting it in local development
        # pins the browser to https://localhost, which then fails to connect.
        self.hsts = hsts

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        path = request.url.path
        response.headers["Content-Security-Policy"] = (
            _DOCS_CSP if path.startswith(_DOCS_PATHS) else _API_CSP
        )
        # Stops a browser from second-guessing a declared content type, which
        # is how a JSON response ends up executed as script.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Nothing here needs a camera, mic or geolocation.
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if self.hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
