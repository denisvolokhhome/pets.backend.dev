"""Integration tests for billing security features.

Feature: billing-service, Property 20: Rate limiting enforcement
"""

import os

# Set test environment BEFORE any app imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test_secret_key_at_least_32_characters_long_for_security")
os.environ.setdefault("BILLING_ENCRYPTION_KEY", "test-encryption-key-for-billing")

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from hypothesis import given, settings as hypothesis_settings, HealthCheck, assume
from hypothesis import strategies as st
from httpx import AsyncClient, ASGITransport

from app.middleware.billing_rate_limiter import READ_LIMIT


# Feature: billing-service, Property 20: Rate limiting enforcement
class TestRateLimitingEnforcement:
    """Property 20: For any user sending requests exceeding the rate limit,
    verify HTTP 429 responses are returned.

    **Validates: Requirements 11.6**
    """

    @pytest.mark.asyncio
    @hypothesis_settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_extra_requests=st.integers(min_value=1, max_value=10),
    )
    async def test_rate_limiting_returns_429_when_limit_exceeded(
        self,
        num_extra_requests: int,
        async_session,
    ):
        """For any user sending more than the rate limit of requests,
        requests beyond the limit receive HTTP 429 responses.

        **Validates: Requirements 11.6**
        """
        from app.main import app
        from app.database import get_async_session

        max_requests, window = READ_LIMIT  # 60 requests per 60 seconds

        # We simulate Redis behaviour via a mock.  The counter starts at 0
        # and increments on each call to ``incr``.  Once the counter exceeds
        # ``max_requests`` the middleware returns 429.
        call_counter = {"value": 0}

        async def mock_incr(key):
            call_counter["value"] += 1
            return call_counter["value"]

        async def mock_expire(key, ttl):
            pass

        async def mock_ttl(key):
            return window

        async def mock_ping():
            return True

        # Build a mock Redis instance that the middleware will use
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=mock_incr)
        mock_redis.expire = AsyncMock(side_effect=mock_expire)
        mock_redis.ttl = AsyncMock(side_effect=mock_ttl)
        mock_redis.ping = AsyncMock(side_effect=mock_ping)

        # Override DB session
        async def override_session():
            yield async_session

        app.dependency_overrides[get_async_session] = override_session

        try:
            # Patch the middleware's _get_redis to return our mock
            # We need to patch on the middleware instance attached to the app.
            # The middleware is registered on the app; we patch _get_redis
            # on the BillingRateLimiterMiddleware class.
            with patch(
                "app.middleware.billing_rate_limiter.BillingRateLimiterMiddleware._get_redis",
                return_value=mock_redis,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    # Send exactly max_requests — all should succeed (200)
                    success_count = 0
                    for _ in range(max_requests):
                        resp = await client.get("/api/billing/plans")
                        if resp.status_code == 200:
                            success_count += 1

                    assert success_count == max_requests, (
                        f"Expected {max_requests} successful requests, got {success_count}"
                    )

                    # Send num_extra_requests beyond the limit — all should get 429
                    rejected_count = 0
                    for _ in range(num_extra_requests):
                        resp = await client.get("/api/billing/plans")
                        if resp.status_code == 429:
                            rejected_count += 1
                            # Verify Retry-After header is present
                            assert "retry-after" in resp.headers, (
                                "429 response missing Retry-After header"
                            )
                            # Verify response body
                            body = resp.json()
                            assert body.get("error_code") == "RATE_LIMITED"

                    assert rejected_count == num_extra_requests, (
                        f"Expected {num_extra_requests} rejected requests (429), "
                        f"got {rejected_count}"
                    )

                    # Verify total successful requests did not exceed the limit
                    assert success_count <= max_requests, (
                        f"Successful requests ({success_count}) exceeded limit ({max_requests})"
                    )
        finally:
            app.dependency_overrides.clear()
