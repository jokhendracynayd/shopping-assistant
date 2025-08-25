"""Rate limiting middleware using Redis backend.

Implements sliding window rate limiting with configurable limits per endpoint
and per client IP address.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi import Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.database.redis_client import execute_redis_operation
from app.models.response import Response as APIResponse
from app.utils.errors import ErrorCode
from app.utils.logger import get_logger

logger = get_logger("middleware.rate_limiting")


class RateLimitConfig:
    """Configuration for rate limiting rules."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10,
        exempt_paths: list[str] | None = None,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_size = burst_size
        self.exempt_paths = exempt_paths or ["/health", "/health/live", "/health/ready"]


# Default rate limiting configurations by endpoint type
RATE_LIMIT_CONFIGS = {
    # Health endpoints - very permissive
    "health": RateLimitConfig(requests_per_minute=300, requests_per_hour=3600),
    # Query endpoints - moderate limits
    "query": RateLimitConfig(requests_per_minute=30, requests_per_hour=500, burst_size=5),
    # Document ingestion - more restrictive
    "ingestion": RateLimitConfig(requests_per_minute=10, requests_per_hour=100, burst_size=2),
    # Default for other endpoints
    "default": RateLimitConfig(requests_per_minute=60, requests_per_hour=1000, burst_size=10),
}


class RateLimiter:
    """Redis-backed rate limiter with sliding window algorithm."""

    def __init__(self, config: RateLimitConfig):
        self.config = config

    async def _get_client_identifier(self, request: Request) -> str:
        """Get unique identifier for the client."""
        # Try to get real IP from headers (when behind proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP if there are multiple
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        # Include user agent for additional uniqueness
        user_agent = request.headers.get("User-Agent", "unknown")[:50]  # Truncate
        return f"rate_limit:{client_ip}:{hash(user_agent) % 10000}"

    async def _sliding_window_check(
        self, redis_key: str, window_seconds: int, max_requests: int
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using sliding window algorithm.

        Returns:
            (is_allowed, current_count, time_until_reset)
        """

        async def _window_operation(client, key: str, window: int, max_req: int):
            current_time = time.time()
            window_start = current_time - window

            pipe = client.pipeline()

            # Remove expired entries
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(current_time): current_time})

            # Set expiration
            pipe.expire(key, window + 1)

            results = await pipe.execute()
            current_count = results[1]  # Count after cleanup

            is_allowed = current_count < max_req
            time_until_reset = int(window - (current_time % window))

            return is_allowed, current_count + 1, time_until_reset

        try:
            return await execute_redis_operation(
                _window_operation, redis_key, window_seconds, max_requests
            )
        except Exception as e:
            logger.debug(f"Rate limiting check failed (Redis unavailable): {e}")
            # Fail open - allow request if Redis is down
            return True, 0, 0

    async def check_rate_limit(self, request: Request) -> tuple[bool, dict[str, Any]]:
        """
        Check if request should be rate limited.

        Returns:
            (is_allowed, rate_limit_info)
        """
        client_id = await self._get_client_identifier(request)

        # Check minute window
        minute_key = f"{client_id}:minute"
        minute_allowed, minute_count, minute_reset = await self._sliding_window_check(
            minute_key, 60, self.config.requests_per_minute
        )

        # Check hour window
        hour_key = f"{client_id}:hour"
        hour_allowed, hour_count, hour_reset = await self._sliding_window_check(
            hour_key, 3600, self.config.requests_per_hour
        )

        # Check burst protection (last 10 seconds)
        burst_key = f"{client_id}:burst"
        burst_allowed, burst_count, _ = await self._sliding_window_check(
            burst_key, 10, self.config.burst_size
        )

        is_allowed = minute_allowed and hour_allowed and burst_allowed

        rate_limit_info = {
            "minute_limit": self.config.requests_per_minute,
            "minute_remaining": max(0, self.config.requests_per_minute - minute_count),
            "minute_reset": minute_reset,
            "hour_limit": self.config.requests_per_hour,
            "hour_remaining": max(0, self.config.requests_per_hour - hour_count),
            "hour_reset": hour_reset,
            "burst_limit": self.config.burst_size,
            "burst_remaining": max(0, self.config.burst_size - burst_count),
        }

        if not is_allowed:
            # Determine which limit was exceeded
            if not minute_allowed:
                rate_limit_info["limit_exceeded"] = "minute"
                rate_limit_info["retry_after"] = minute_reset
            elif not hour_allowed:
                rate_limit_info["limit_exceeded"] = "hour"
                rate_limit_info["retry_after"] = hour_reset
            else:
                rate_limit_info["limit_exceeded"] = "burst"
                rate_limit_info["retry_after"] = 10

        return is_allowed, rate_limit_info


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self.rate_limiters = {
            endpoint_type: RateLimiter(config)
            for endpoint_type, config in RATE_LIMIT_CONFIGS.items()
        }

    def _get_endpoint_type(self, path: str) -> str:
        """Determine endpoint type for rate limiting rules."""
        if path.startswith("/health"):
            return "health"
        if "/query" in path:
            return "query"
        if "/add-documents" in path:
            return "ingestion"
        return "default"

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        # Always exempt health checks
        if path.startswith("/health"):
            return True

        # Check other exempt paths
        exempt_paths = ["/docs", "/redoc", "/openapi.json"]
        return any(path.startswith(exempt) for exempt in exempt_paths)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip rate limiting for exempt paths
        if self._is_exempt_path(path):
            return await call_next(request)

        # Get appropriate rate limiter
        endpoint_type = self._get_endpoint_type(path)
        rate_limiter = self.rate_limiters[endpoint_type]

        # Check rate limit
        try:
            is_allowed, rate_info = await rate_limiter.check_rate_limit(request)

            if not is_allowed:
                logger.warning(
                    f"Rate limit exceeded for {request.client.host if request.client else 'unknown'} "
                    f"on {path} ({rate_info.get('limit_exceeded')} limit)"
                )

                # Create rate limit response
                error_response = APIResponse(
                    success=False,
                    error={
                        "code": ErrorCode.RATE_LIMIT_EXCEEDED.value,
                        "message": f"Rate limit exceeded. Too many requests per {rate_info.get('limit_exceeded', 'time period')}.",
                        "details": {
                            "limit_exceeded": rate_info.get("limit_exceeded"),
                            "retry_after": rate_info.get("retry_after"),
                            "limits": {
                                "minute": f"{rate_info['minute_remaining']}/{rate_info['minute_limit']}",
                                "hour": f"{rate_info['hour_remaining']}/{rate_info['hour_limit']}",
                            },
                        },
                    },
                )

                response = JSONResponse(
                    status_code=429,
                    content=error_response.dict(),
                    headers={
                        "X-RateLimit-Limit-Minute": str(rate_info["minute_limit"]),
                        "X-RateLimit-Remaining-Minute": str(rate_info["minute_remaining"]),
                        "X-RateLimit-Reset-Minute": str(rate_info["minute_reset"]),
                        "X-RateLimit-Limit-Hour": str(rate_info["hour_limit"]),
                        "X-RateLimit-Remaining-Hour": str(rate_info["hour_remaining"]),
                        "X-RateLimit-Reset-Hour": str(rate_info["hour_reset"]),
                        "Retry-After": str(rate_info.get("retry_after", 60)),
                    },
                )
                return response

        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            # Continue processing if rate limiting fails

        # Process request normally
        response = await call_next(request)

        # Add rate limit headers to successful responses
        try:
            _, rate_info = await rate_limiter.check_rate_limit(request)
            response.headers["X-RateLimit-Limit-Minute"] = str(rate_info["minute_limit"])
            response.headers["X-RateLimit-Remaining-Minute"] = str(rate_info["minute_remaining"])
            response.headers["X-RateLimit-Limit-Hour"] = str(rate_info["hour_limit"])
            response.headers["X-RateLimit-Remaining-Hour"] = str(rate_info["hour_remaining"])
        except Exception:
            pass  # Don't fail the response if we can't add headers

        return response
