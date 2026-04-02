"""API dependencies — authentication and common parameters."""

from __future__ import annotations

from fastapi import Header, HTTPException

from config.settings import DEFAULT_API_SECRET_KEY, settings


def require_api_key(x_api_key: str = Header(...)) -> str:
    """Validate X-API-Key header for write endpoints.

    Raises 401 if the key is missing or doesn't match API_SECRET_KEY.
    Raises 503 if API_SECRET_KEY was never configured (still default).
    """
    if settings.api.secret_key == DEFAULT_API_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="API_SECRET_KEY not configured. Set it in .env before using write endpoints.",
        )
    if x_api_key != settings.api.secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
