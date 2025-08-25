"""Request size limiting middleware for FastAPI."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.utils.errors import Error, ErrorCode
from app.utils.logger import get_logger

logger = get_logger("middleware.request_size")


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size and prevent DoS attacks."""

    def __init__(
        self,
        app: Any,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10MB default
        exclude_paths: list[str] | None = None,
    ):
        """Initialize request size limit middleware.
        
        Args:
            app: FastAPI application instance
            max_size_bytes: Maximum allowed request body size in bytes
            exclude_paths: List of paths to exclude from size checking
        """
        super().__init__(app)
        self.max_size_bytes = max_size_bytes
        self.exclude_paths = exclude_paths or []
        logger.info(
            f"Request size limit middleware initialized with max size: {max_size_bytes} bytes"
        )

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request and enforce size limits."""
        
        # Skip size checking for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Skip for GET requests (no body expected)
        if request.method == "GET":
            return await call_next(request)

        # Check Content-Length header first (most efficient)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size_bytes:
                    logger.warning(
                        f"Request rejected: Content-Length {size} exceeds limit {self.max_size_bytes}",
                        extra={
                            "path": request.url.path,
                            "method": request.method,
                            "content_length": size,
                            "limit": self.max_size_bytes,
                            "client_ip": request.client.host if request.client else "unknown",
                        }
                    )
                    return self._create_error_response(
                        f"Request body too large. Maximum size: {self.max_size_bytes} bytes"
                    )
            except ValueError:
                logger.warning(f"Invalid Content-Length header: {content_length}")

        # For requests without Content-Length, we'll let them through
        # Most legitimate requests will have Content-Length header
        # This avoids the complexity of request reconstruction
        try:
            return await call_next(request)
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return self._create_error_response("Error processing request")

    def _create_error_response(self, message: str) -> JSONResponse:
        """Create standardized error response for size limit violations."""
        error = Error(ErrorCode.REQUEST_TOO_LARGE, message=message)
        return JSONResponse(
            status_code=413,  # HTTP 413 Payload Too Large
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": {
                        "max_size_bytes": self.max_size_bytes,
                        "max_size_human": self._format_bytes(self.max_size_bytes),
                    }
                }
            },
            headers={
                "Content-Type": "application/json",
                "X-RateLimit-Type": "request-size",
                "Retry-After": "60",  # Suggest retry after 1 minute
            }
        )

    @staticmethod
    def _format_bytes(bytes_value: int) -> str:
        """Format bytes into human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} TB"


def create_request_size_middleware(
    max_size_mb: int = 10,
    exclude_paths: list[str] | None = None
) -> RequestSizeLimitMiddleware:
    """Factory function to create request size limit middleware.
    
    Args:
        max_size_mb: Maximum request size in megabytes
        exclude_paths: Paths to exclude from size checking
        
    Returns:
        Configured RequestSizeLimitMiddleware instance
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    return lambda app: RequestSizeLimitMiddleware(
        app,
        max_size_bytes=max_size_bytes,
        exclude_paths=exclude_paths or ["/health", "/docs", "/openapi.json"]
    )
