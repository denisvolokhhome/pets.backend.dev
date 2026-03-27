"""Rate limiting middleware to prevent abuse."""
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import hashlib
import hmac


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


# Global rate limiter instance
rate_limiter = RateLimiter()


async def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    
    Handles X-Forwarded-For header for proxied requests.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
