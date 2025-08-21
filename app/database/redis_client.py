"""Redis client configuration and helper for the application.

Provides a connection pool based on settings in `app.config`.
"""
from typing import Optional
import redis.asyncio as redis

from app.config import settings


_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, max_connections=settings.redis_max_connections)
    return _client


async def ping() -> bool:
    try:
        r = get_redis_client()
        return await r.ping()
    except Exception:
        return False


