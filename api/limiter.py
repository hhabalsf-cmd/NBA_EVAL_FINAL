"""Shared rate-limiter instance.

Defined here (not in main.py) so routers can import it without circular deps.
"""
from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    """Extract real client IP from X-Forwarded-For (Railway/reverse proxy) or fall back to peer IP."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2 — leftmost is the real client
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(
    key_func=_get_real_ip,
    default_limits=["120/minute"],
)
