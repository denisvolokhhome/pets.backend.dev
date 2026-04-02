"""Security headers middleware for billing endpoints."""
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class BillingSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that adds security headers to all ``/api/billing/``
    responses.

    Headers applied:
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Cache-Control: no-store
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.url.path.startswith("/api/billing/"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Cache-Control"] = "no-store"

        return response
