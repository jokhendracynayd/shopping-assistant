"""Redis-backed cache helpers."""

import hashlib
import json
from typing import Any

from app.config import settings


def cache_key(prefix: str, *args: Any) -> str:
    """Generate a cache key from prefix and arguments."""
    # Create a deterministic key from the arguments
    key_parts = [str(prefix)]
    for arg in args:
        if isinstance(arg, (dict, list)):
            # For complex objects, create a hash
            arg_str = json.dumps(arg, sort_keys=True)
        else:
            arg_str = str(arg)
        key_parts.append(arg_str)

    key_string = ":".join(key_parts)

    # If key is too long, hash it
    if len(key_string) > 200:
        hash_obj = hashlib.md5(key_string.encode())
        return f"{prefix}:hash:{hash_obj.hexdigest()}"

    return key_string


async def get_cached_response(key: str) -> Any | None:
    """Get cached response by key."""
    try:
        from app.database.redis_client import get_redis_client

        client = await get_redis_client()
        if client is None:
            return None

        raw = await client.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        # swallow cache errors to avoid failing requests
        return None


async def set_cached_response(key: str, value: Any, ttl: int | None = None) -> None:
    """Set cached response with optional TTL."""
    try:
        from app.database.redis_client import get_redis_client

        client = await get_redis_client()
        if client is None:
            return

        raw = json.dumps(value)
        await client.set(key, raw, ex=ttl or settings.cache_ttl_seconds)
    except Exception:
        # ignore cache errors
        return


# Alias for compatibility
async def cache_response(key: str, value: Any, ttl: int = 300) -> None:
    """Alias for set_cached_response with explicit TTL."""
    await set_cached_response(key, value, ttl)
