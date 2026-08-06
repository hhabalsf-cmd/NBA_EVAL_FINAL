"""Custom ASGI middleware for the API.

Kept separate from main.py so tests can import these without pulling in the
full application (routers, DB pool, model storage).

Middleware order is defined in main.py — add_middleware() wraps outside-in,
so the LAST one added is the OUTERMOST.
"""
import logging

from fastapi import Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CatchAllExceptionMiddleware:
    """Turn unhandled exceptions into JSON 500s from INSIDE the CORS layer.

    Starlette's default ServerErrorMiddleware sits outside all user
    middleware, so its 500s carry no CORS headers and the browser reports an
    opaque network error instead of the real failure. This must be added
    immediately BEFORE CORSMiddleware in main.py (i.e. wrapped by it) so
    error responses pass through CORS and get the headers.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            logger.exception(
                "Unhandled exception on %s %s",
                scope.get("method"), scope.get("path"),
            )
            if response_started:
                raise  # Too late to send a fresh response — let the server abort
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
            await response(scope, receive, send)


class SelectiveGZipMiddleware:
    """GZip that passes Server-Sent Events through uncompressed.

    Starlette's GZipMiddleware buffers streamed response bodies, which holds
    back every SSE progress event until the stream closes — the frontend
    progress bars sit frozen at 0% and jump to done. Requests that accept
    text/event-stream bypass compression entirely; everything else gets the
    normal GZip path.
    """

    def __init__(self, app, minimum_size: int = 1000):
        self.app = app
        self.gzip_app = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            if "text/event-stream" in headers.get("accept", ""):
                await self.app(scope, receive, send)
                return
        await self.gzip_app(scope, receive, send)


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies larger than the configured limit (default 2 MB)."""

    MAX_BODY_SIZE = 2 * 1024 * 1024  # 2 MB

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-relevant HTTP response headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co;"
        )
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
