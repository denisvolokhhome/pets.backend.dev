"""Rate limiting middleware to prevent abuse."""
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import hashlib
import hmac
import logging
import os
import time
import uuid
from typing import Mapping, Optional

from app.config import Settings

_settings = Settings()
logger = logging.getLogger(__name__)


# Secret key for IP hashing — loaded from settings at runtime
_IP_HASH_KEY: str = ""


def set_ip_hash_key(key: str) -> None:
    """Set the HMAC key for IP hashing (call once at startup)."""
    global _IP_HASH_KEY
    _IP_HASH_KEY = key


def hash_ip(ip: str) -> str:
    """
    Hash an IP address using HMAC-SHA256 with a secret key.
    Returns a hex digest that can be stored/compared safely.
    """
    key = (_IP_HASH_KEY or "fallback-key").encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


class RateLimiter:
    """
    Sliding-window rate limiter.

    Hits are kept in Redis (one sorted set per key) so every uvicorn worker and container
    shares the same counters. If Redis is not configured or is unreachable, it falls back
    to per-process memory: limits stay enforced, only looser by the number of processes.
    Tests (TESTING=1) always use memory; reset it with ``rate_limiter.requests.clear()``.
    """

    REDIS_PREFIX = "rl:"
    REDIS_RETRY_SECONDS = 30
    RECORD_TTL_SECONDS = 86400  # record() has no window; ensure_below() trims by its own

    def __init__(self, redis_url: Optional[str] = None):
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()
        self._redis_url = redis_url
        self._redis = None
        self._redis_retry_at = 0.0

    # ── Redis backend ─────────────────────────────────────────────────
    async def _redis_client(self):
        if not self._redis_url:
            return None
        if self._redis is not None:
            return self._redis
        if time.monotonic() < self._redis_retry_at:
            return None
        try:
            from redis.asyncio import Redis
            client = Redis.from_url(
                self._redis_url, decode_responses=True,
                socket_timeout=1, socket_connect_timeout=1,
            )
            await client.ping()
            self._redis = client
            return client
        except Exception as exc:  # noqa: BLE001 — fall back to memory, retry later
            self._redis_down(exc)
            return None

    def _redis_down(self, exc: Exception) -> None:
        logger.warning("Rate limiter: Redis unavailable (%s); using per-process memory", exc)
        self._redis = None
        self._redis_retry_at = time.monotonic() + self.REDIS_RETRY_SECONDS

    async def _redis_hit(self, key: str, max_requests: int, window_seconds: int) -> Optional[bool]:
        """Record a hit unless the window is full. True = allowed, False = limited, None = no Redis."""
        client = await self._redis_client()
        if client is None:
            return None
        rkey, now = self.REDIS_PREFIX + key, time.time()
        member = f"{now}:{uuid.uuid4().hex}"
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(rkey, 0, now - window_seconds)
                pipe.zadd(rkey, {member: now})
                pipe.zcard(rkey)
                pipe.expire(rkey, window_seconds)
                count = (await pipe.execute())[2]
            if count > max_requests:
                await client.zrem(rkey, member)  # a refused request doesn't use up the window
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            self._redis_down(exc)
            return None

    async def _redis_count(self, key: str, window_seconds: int) -> Optional[int]:
        client = await self._redis_client()
        if client is None:
            return None
        rkey, now = self.REDIS_PREFIX + key, time.time()
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(rkey, 0, now - window_seconds)
                pipe.zcard(rkey)
                return (await pipe.execute())[1]
        except Exception as exc:  # noqa: BLE001
            self._redis_down(exc)
            return None

    async def _redis_record(self, key: str) -> bool:
        client = await self._redis_client()
        if client is None:
            return False
        rkey, now = self.REDIS_PREFIX + key, time.time()
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.zadd(rkey, {f"{now}:{uuid.uuid4().hex}": now})
                pipe.expire(rkey, self.RECORD_TTL_SECONDS)
                await pipe.execute()
            return True
        except Exception as exc:  # noqa: BLE001
            self._redis_down(exc)
            return False

    # ── Public API ────────────────────────────────────────────────────
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int = 5,
        window_seconds: int = 300  # 5 minutes
    ) -> bool:
        """
        Check if request is within rate limit, and count it.

        Args:
            key: Unique identifier (e.g., IP address or email)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            bool: True if within limit, raises HTTPException if exceeded
        """
        detail = f"Too many requests. Please try again in {window_seconds // 60} minutes."
        allowed = await self._redis_hit(key, max_requests, window_seconds)
        if allowed is False:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
        if allowed:
            return True

        async with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=window_seconds)

            # Remove old requests
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if req_time > cutoff
            ]

            # Check if limit exceeded
            if len(self.requests[key]) >= max_requests:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)

            # Add current request
            self.requests[key].append(now)
            return True

    async def ensure_below(self, key: str, max_requests: int, window_seconds: int, detail: str) -> None:
        """Raise 429 if `key` already has `max_requests` hits in the window, without recording one."""
        count = await self._redis_count(key, window_seconds)
        if count is not None:
            if count >= max_requests:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
            return
        async with self.lock:
            cutoff = datetime.now() - timedelta(seconds=window_seconds)
            self.requests[key] = [t for t in self.requests[key] if t > cutoff]
            if len(self.requests[key]) >= max_requests:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)

    async def record(self, key: str) -> None:
        """Record one hit for `key` (pair with ensure_below to count only some outcomes)."""
        if await self._redis_record(key):
            return
        async with self.lock:
            self.requests[key].append(datetime.now())

    async def reset(self, key: str) -> None:
        client = await self._redis_client()
        if client is not None:
            try:
                await client.delete(self.REDIS_PREFIX + key)
            except Exception as exc:  # noqa: BLE001
                self._redis_down(exc)
        async with self.lock:
            self.requests.pop(key, None)


# Global rate limiter instance: shared across workers via Redis, memory-only under tests
rate_limiter = RateLimiter(None if os.environ.get("TESTING") == "1" else _settings.redis_url)


def resolve_client_ip(
    headers: Mapping[str, str],
    peer: Optional[str],
    client_ip_header: str = "",
    trusted_proxy_hops: int = 1,
) -> str:
    """
    Work out the real client IP without trusting anything the client can forge.

    Proxies append the address they received the request from to X-Forwarded-For, so
    only the rightmost ``trusted_proxy_hops`` entries were written by our own proxies;
    everything to the left of them is client-supplied and must be ignored. An edge
    header such as Cloudflare's CF-Connecting-IP is preferred when configured.
    """
    if client_ip_header:
        value = headers.get(client_ip_header, "").split(",")[0].strip()
        if value:
            return value
    forwarded = headers.get("X-Forwarded-For")
    if forwarded and trusted_proxy_hops > 0:
        hosts = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hosts:
            return hosts[-min(trusted_proxy_hops, len(hosts))]
    return peer or "unknown"


def client_ip(request: Request) -> str:
    """Client IP for rate limiting, per the CLIENT_IP_HEADER / TRUSTED_PROXY_HOPS settings."""
    return resolve_client_ip(
        request.headers,
        request.client.host if request.client else None,
        _settings.client_ip_header,
        _settings.trusted_proxy_hops,
    )


async def get_client_ip(request: Request) -> str:
    """Async alias of client_ip() kept for existing callers."""
    return client_ip(request)
