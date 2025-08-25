"""Redis client configuration and helper for the application.

Provides a robust Redis connection with:
- Connection pooling with health monitoring
- Automatic reconnection and circuit breaker
- Timeout handling and error recovery
- Performance monitoring and logging
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("database.redis")


class RedisManager:
    """Redis connection manager with health monitoring and auto-recovery."""

    def __init__(self):
        self._client: redis.Redis | None = None
        self._pool: ConnectionPool | None = None
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        self._is_healthy = True
        self._consecutive_failures = 0
        self._max_failures = 3

    async def _create_pool(self) -> ConnectionPool:
        """Create Redis connection pool with proper configuration."""
        return ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            retry_on_timeout=True,
            retry_on_error=[redis.ConnectionError, redis.TimeoutError],
            health_check_interval=30,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=True,
            encoding="utf-8",
        )

    async def _initialize_client(self) -> redis.Redis:
        """Initialize Redis client with connection pool."""
        if self._pool is None:
            self._pool = await self._create_pool()

        client = redis.Redis(connection_pool=self._pool)

        # Test connection
        try:
            await asyncio.wait_for(client.ping(), timeout=5.0)
            logger.info("Redis client initialized successfully")
            self._consecutive_failures = 0
            self._is_healthy = True
            return client
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
            self._consecutive_failures += 1
            self._is_healthy = False
            # Return client anyway - it might work later
            return client

    async def get_client(self) -> redis.Redis:
        """Get Redis client with health check and auto-recovery."""
        current_time = time.time()

        # Check if we need a health check
        if (current_time - self._last_health_check) > self._health_check_interval:
            await self._health_check()
            self._last_health_check = current_time

        # Initialize client if needed
        if self._client is None or not self._is_healthy:
            if self._consecutive_failures >= self._max_failures:
                logger.info("Redis client in circuit breaker mode, attempting recovery")
                await asyncio.sleep(1)  # Brief backoff

            try:
                self._client = await self._initialize_client()
            except Exception as e:
                logger.warning(f"Failed to get Redis client: {e}")
                # Don't raise exception - return None and let callers handle gracefully
                self._client = None

        return self._client

    async def _health_check(self) -> bool:
        """Perform health check on Redis connection."""
        if self._client is None:
            self._is_healthy = False
            return False

        try:
            await asyncio.wait_for(self._client.ping(), timeout=2.0)
            self._is_healthy = True
            self._consecutive_failures = 0
            logger.debug("Redis health check passed")
            return True
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            self._is_healthy = False
            self._consecutive_failures += 1
            return False

    async def close(self) -> None:
        """Close Redis connections gracefully."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")
            finally:
                self._client = None

        if self._pool:
            try:
                await self._pool.aclose()
            except Exception as e:
                logger.warning(f"Error closing Redis pool: {e}")
            finally:
                self._pool = None

        logger.info("Redis connections closed")

    @asynccontextmanager
    async def get_client_context(self) -> AsyncGenerator[redis.Redis]:
        """Context manager for Redis client with automatic error handling."""
        client = None
        try:
            client = await self.get_client()
            yield client
        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            self._is_healthy = False
            raise
        except redis.TimeoutError as e:
            logger.error(f"Redis timeout error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            raise

    async def execute_with_retry(self, operation, *args, max_retries: int = 3, **kwargs) -> Any:
        """Execute Redis operation with retry logic."""
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                async with self.get_client_context() as client:
                    return await operation(client, *args, **kwargs)
            except (redis.ConnectionError, redis.TimeoutError) as e:
                last_exception = e
                if attempt < max_retries:
                    wait_time = (2**attempt) * 0.5  # Exponential backoff
                    logger.warning(
                        f"Redis operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Redis operation failed after {max_retries + 1} attempts")

        raise last_exception or redis.ConnectionError("Redis operation failed")


# Global Redis manager instance
_redis_manager = RedisManager()


async def get_redis_client() -> redis.Redis | None:
    """Get Redis client - main entry point for the application."""
    return await _redis_manager.get_client()


async def ping() -> bool:
    """Check Redis connectivity."""
    try:
        client = await get_redis_client()
        if client is None:
            return False
        await client.ping()
        return True
    except Exception:
        return False


async def get_redis_info() -> dict:
    """Get Redis server information for health checks."""
    try:
        client = await get_redis_client()
        if client is None:
            return {"connected": False, "error": "Redis client not available"}

        info = await client.info()
        return {
            "connected": True,
            "version": info.get("redis_version"),
            "memory_used": info.get("used_memory_human"),
            "connections": info.get("connected_clients"),
            "uptime_seconds": info.get("uptime_in_seconds"),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


async def execute_redis_operation(operation, *args, **kwargs):
    """Execute Redis operation with built-in retry and error handling."""
    return await _redis_manager.execute_with_retry(operation, *args, **kwargs)


async def close_redis_connections():
    """Close all Redis connections - call during app shutdown."""
    await _redis_manager.close()
