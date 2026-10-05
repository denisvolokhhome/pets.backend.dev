"""Rate limiting middleware to prevent abuse."""
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import hashlib
import hmac
from typing import Mapping, Optional

from app.config import Settings

_settings = Settings()


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
    Simple in-memory rate limiter.
    
    For production, consider using Redis-based rate limiting.
    """
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int = 5,
        window_seconds: int = 300  # 5 minutes
    ) -> bool:
        """
        Check if request is within rate limit.
        
        Args:
            key: Unique identifier (e.g., IP address or email)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
            
        Returns:
            bool: True if within limit, raises HTTPException if exceeded
        """
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
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Please try again in {window_seconds // 60} minutes."
                )
            
            # Add current request
            self.requests[key].append(now)
            return True


    async def ensure_below(self, key: str, max_requests: int, window_seconds: int, detail: str) -> None:
        """Raise 429 if `key` already has `max_requests` hits in the window, without recording one."""
        async with self.lock:
            cutoff = datetime.now() - timedelta(seconds=window_seconds)
            self.requests[key] = [t for t in self.requests[key] if t > cutoff]
            if len(self.requests[key]) >= max_requests:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)

    async def record(self, key: str) -> None:
        """Record one hit for `key` (pair with ensure_below to count only some outcomes)."""
        async with self.lock:
            self.requests[key].append(datetime.now())

    async def reset(self, key: str) -> None:
        async with self.lock:
            self.requests.pop(key, None)


# Global rate limiter instance
rate_limiter = RateLimiter()


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
