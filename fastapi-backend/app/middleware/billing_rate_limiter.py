"""Rate limiting middleware for billing endpoints using Redis sliding window counters."""
import logging
from typing import Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import Settings

logger = logging.getLogger(__name__)

# Rate limit tiers: (max_requests, window_seconds)
MUTATION_LIMIT: Tuple[int, int] = (30, 60)
READ_LIMIT: Tuple[int, int] = (60, 60)
WEBHOOK_LIMIT: Tuple[int, int] = (120, 60)

# Billing paths classified by tier
MUTATION_PATHS = {
    "/api/billing/subscribe",
    "/api/billing/create-checkout-session",
}
WEBHOOK_PATHS = {
    "/api/billing/webhook",
}
READ_PATHS = {
    "/api/billing/plans",
    "/api/billing/subscription",
    "/api/billing/invoices",
}


def _classify_request(path: str, method: str) -> Optional[Tuple[int, int]]:
    """Return (max_requests, window_seconds) for a billing path, or None if not a billing path."""
    if not path.startswith("/api/billing/"):
        return None

    if method == "POST" and path in MUTATION_PATHS:
        return MUTATION_LIMIT
    if method == "POST" and path in WEBHOOK_PATHS:
        return WEBHOOK_LIMIT
    if method == "GET" and path in READ_PATHS:
        return READ_LIMIT

    # Default: treat unknown billing paths as read-tier
    if method == "GET":
        return READ_LIMIT
    return MUTATION_LIMIT


def _get_client_identifier(request: Request) -> str:
    """
    Extract a rate-limit key from the request.

    Uses the authenticated user ID when available (set by auth middleware on
    ``request.state.user``), otherwise falls back to the client IP address
    (respecting X-Forwarded-For for proxied requests).
    """
    try:
        if hasattr(request.state, "user") and request.state.user is not None:
            return f"user:{request.state.user.id}"
    except Exception:
        pass

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


class BillingRateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces per-user/IP sliding window rate limits
    on ``/api/billing/`` endpoints using Redis.

    If Redis is unavailable the request is allowed through (graceful degradation).
    """

    def __init__(self, app: ASGIApp, redis_url: Optional[str] = None) -> None:
        super().__init__(app)
        self._redis_url = redis_url or Settings().redis_url
        self._redis: Optional[Redis] = None

    async def _get_redis(self) -> Optional[Redis]:
        """Lazily connect to Redis; return None on failure."""
        if self._redis is not None:
            return self._redis
        try:
            self._redis = Redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            return self._redis
        except Exception as exc:
            logger.warning("Billing rate limiter: Redis unavailable (%s). Allowing request.", exc)
            self._redis = None
            return None

    async def dispatch(self, request: Request, call_next):
        limit_config = _classify_request(request.url.path, request.method)
        if limit_config is None:
            # Not a billing endpoint — skip rate limiting
            return await call_next(request)

        max_requests, window = limit_config

        redis = await self._get_redis()
        if redis is None:
            # Redis down — allow the request through
            return await call_next(request)

        client_key = _get_client_identifier(request)
        redis_key = f"billing_rl:{client_key}:{request.url.path}:{request.method}"

        try:
            current_count = await redis.incr(redis_key)
            if current_count == 1:
                # First request in this window — set expiry
                await redis.expire(redis_key, window)

            if current_count > max_requests:
                ttl = await redis.ttl(redis_key)
                retry_after = max(ttl, 1)
                logger.info(
                    "Rate limit exceeded for %s on %s %s (%d/%d)",
                    client_key,
                    request.method,
                    request.url.path,
                    current_count,
                    max_requests,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please try again later.",
                        "error_code": "RATE_LIMITED",
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        except Exception as exc:
            # Redis error mid-request — degrade gracefully
            logger.warning("Billing rate limiter: Redis error (%s). Allowing request.", exc)

        return await call_next(request)
