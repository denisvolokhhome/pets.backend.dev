"""RateLimiter falls back to per-process memory when Redis is unreachable."""

import pytest
from fastapi import HTTPException

from app.middleware.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_unreachable_redis_still_enforces_limits_in_memory():
    limiter = RateLimiter("redis://127.0.0.1:1/0")  # nothing listens on port 1

    await limiter.check_rate_limit("k", max_requests=2, window_seconds=60)
    await limiter.check_rate_limit("k", max_requests=2, window_seconds=60)
    with pytest.raises(HTTPException) as exc:
        await limiter.check_rate_limit("k", max_requests=2, window_seconds=60)
    assert exc.value.status_code == 429

    await limiter.record("f")
    with pytest.raises(HTTPException):
        await limiter.ensure_below("f", max_requests=1, window_seconds=60, detail="locked")
    await limiter.reset("f")
    await limiter.ensure_below("f", max_requests=1, window_seconds=60, detail="locked")


@pytest.mark.asyncio
async def test_redis_is_not_retried_on_every_call():
    limiter = RateLimiter("redis://127.0.0.1:1/0")
    assert await limiter._redis_client() is None
    assert limiter._redis_retry_at > 0
    # Within the retry window no new connection attempt is made
    limiter._redis_url = "redis://should-not-be-dialed:6379/0"
    assert await limiter._redis_client() is None
