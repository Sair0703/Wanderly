"""Per-IP fixed-window rate limiting, backed by the cache (Redis or memory).

Used to protect auth and write endpoints from brute-force and spam. Works
across instances when Redis is configured; degrades to per-instance limits with
the in-memory cache.
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status

from .cache import cache


def client_ip(request: Request) -> str:
    # Trust the left-most X-Forwarded-For entry set by the TLS proxy (Render/Railway).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limiter(scope: str, limit: int, window: int):
    """Return a FastAPI dependency enforcing `limit` requests per `window` secs."""

    def dependency(request: Request) -> None:
        key = f"rl:{scope}:{client_ip(request)}"
        count = cache.incr(key, window)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(window)},
            )

    return dependency
