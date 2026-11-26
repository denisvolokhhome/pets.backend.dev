"""Shared guard for the internal admin API (/api/admin/*).

The admin API is used only by the breedly-administration portal, which runs on the
local network and calls the backend over the internal docker network. Public traffic
reaches the backend only through the Cloudflare tunnel, and Cloudflare stamps every
such request with CF-Connecting-IP (a client cannot remove it). Requests carrying it
are answered with 404, so the admin API does not exist from the internet even for
someone holding the key.
"""
import secrets

from fastapi import Header, HTTPException, Request

from app.config import Settings

settings = Settings()

PUBLIC_EDGE_HEADER = "cf-connecting-ip"


async def verify_admin_key(request: Request, x_admin_key: str = Header(default="")) -> bool:
    if PUBLIC_EDGE_HEADER in request.headers:
        raise HTTPException(status_code=404, detail="Not Found")
    if not settings.admin_api_key or not secrets.compare_digest(
        x_admin_key.encode(), settings.admin_api_key.encode()
    ):
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return True
