"""Rate limiting middleware for billing endpoints using Redis sliding window counters."""
import logging
from typing import Optional, Tuple

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import Settings

logger = logging.getLogger(__name__)

# Rate limit tiers: (max_requests, window_seconds)
MUTATION_LIMIT: Tuple[int, int] = (30, 60)
READ_LIMIT: Tuple[int, int] = (60, 60)
WEBHOOK_LIMIT: Tuple[int, int] = (120, 60)

MUTATION_PATHS = {
    "/api/billing/subscribe",
    "/api/billing/create-checkout-session",
    "/api/billing/portal-session",
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
    if not path.startswith("/api/billing/"):
        return None
    if method == "POST" and path in MUTATION_PATHS:
        return MUTATION_LIMIT
    if method == "POST" and path in WEBHOOK_PATHS:
        return WEBHOOK_LIMIT
    if method == "GET" and path in READ_PATHS:
        return READ_LIMIT
    if method == "GET":
        return READ_LIMIT
    return MUTATION_LIMIT


def _get_client_identifier(request: Request) -> str:
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


class BillingRateLimiterMiddleware:
    """
    Pure ASGI middleware that enforces per-user/IP sliding window rate limits
    on /api/billing/ endpoints using Redis.

    Uses pure ASGI (not BaseHTTPMiddleware) to avoid body buffering issues
    that would break Stripe webhook signature verification.
    """

    def __init__(self, app: ASGIApp, redis_url: Optional[str] = None) -> None:
        self.app = app
        self._redis_url = redis_url or Settings().redis_url
        self._redis = None

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            from redis.asyncio import Redis
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        path = request.url.path
        method = request.method

        limit_config = _classify_request(path, method)
        if limit_config is None:
            await self.app(scope, receive, send)
            return

        max_requests, window = limit_config
        redis = await self._get_redis()

        if redis is not None:
            client_key = _get_client_identifier(request)
            redis_key = f"billing_rl:{client_key}:{path}:{method}"
            try:
                current_count = await redis.incr(redis_key)
                if current_count == 1:
                    await redis.expire(redis_key, window)
                if current_count > max_requests:
                    ttl = await redis.ttl(redis_key)
                    retry_after = max(ttl, 1)
                    logger.info(
                        "Rate limit exceeded for %s on %s %s (%d/%d)",
                        client_key, method, path, current_count, max_requests,
                    )
                    response = JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Too many requests. Please try again later.",
                            "error_code": "RATE_LIMITED",
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
                    await response(scope, receive, send)
                    return
            except Exception as exc:
                logger.warning("Billing rate limiter: Redis error (%s). Allowing request.", exc)

        await self.app(scope, receive, send)
