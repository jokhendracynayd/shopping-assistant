"""API key security dependency for FastAPI endpoints."""
from fastapi import Header, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from typing import Optional

from app.config import get_allowed_api_keys, settings
from app.utils.errors import create_api_error, ErrorCode


api_key_header = APIKeyHeader(name=settings.api_key_header_name, auto_error=False)


async def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """FastAPI dependency to require a valid API key.

    Looks up allowed keys from environment/config and raises `APIError` when missing/invalid.
    """
    if not settings.require_api_key:
        return ""

    if not api_key:
        raise create_api_error(ErrorCode.UNAUTHORIZED, details={"reason": "missing_api_key"})

    allowed = get_allowed_api_keys()
    if api_key not in allowed:
        raise create_api_error(ErrorCode.FORBIDDEN, details={"reason": "invalid_api_key"})

    return api_key


