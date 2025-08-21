"""Redis-backed cache helpers."""
import json
from typing import Any, Optional

from app.database.redis_client import get_redis_client
from app.config import settings


async def get_cached_response(key: str) -> Optional[Any]:
    try:
        r = get_redis_client()
        raw = await r.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        # swallow cache errors to avoid failing requests
        return None


async def set_cached_response(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        r = get_redis_client()
        raw = json.dumps(value)
        await r.set(key, raw, ex=ttl or settings.cache_ttl_seconds)
    except Exception:
        # ignore cache errors
        return None


