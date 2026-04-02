"""Tests for billing security headers middleware."""
import pytest


@pytest.mark.asyncio
async def test_billing_endpoint_has_security_headers(async_client):
    """Security headers are present on /api/billing/ responses."""
    response = await async_client.get("/api/billing/plans")

    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_non_billing_endpoint_no_security_headers(async_client):
    """Security headers are NOT added to non-billing endpoints."""
    response = await async_client.get("/health")

    assert "X-Frame-Options" not in response.headers
    assert "Strict-Transport-Security" not in response.headers
