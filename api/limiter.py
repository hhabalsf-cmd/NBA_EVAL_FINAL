"""Shared rate-limiter instance.

Defined here (not in main.py) so routers can import it without circular deps.
"""
from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    """Extract real client IP from X-Forwarded-For (Railway/reverse proxy) or fall back to peer IP.

    Uses the RIGHTMOST entry: the client can send an X-Forwarded-For header
    with arbitrary values, but the edge proxy (Railway) APPENDS the address it
    actually saw, so only the last entry is trustworthy. Taking the leftmost
    would let anyone rotate fake IPs to dodge rate limits.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(
    key_func=_get_real_ip,
    default_limits=["120/minute"],
)
