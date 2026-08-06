"""Custom ASGI middleware for the API.

Kept separate from main.py so tests can import these without pulling in the
full application (routers, DB pool, model storage).

Middleware order is defined in main.py — add_middleware() wraps outside-in,
so the LAST one added is the OUTERMOST.
"""
from fastapi import Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware


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
