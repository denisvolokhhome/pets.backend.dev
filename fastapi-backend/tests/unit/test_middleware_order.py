"""Middleware ordering guarantees for the FastAPI app."""
from starlette.middleware.cors import CORSMiddleware

from app.main import app


def test_cors_is_outermost_middleware():
    """CORS must wrap every other middleware.

    Starlette runs the last-added middleware outermost. If CORS sits inside the
    billing rate limiter, the limiter's 429 responses go out without CORS headers
    and browsers report them as opaque network errors ("Error 0").
    """
    # user_middleware is ordered outermost first
    assert app.user_middleware[0].cls is CORSMiddleware
