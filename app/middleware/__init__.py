"""Middleware package for the shopping assistant application."""

from .rate_limiting import RateLimitingMiddleware

__all__ = ["RateLimitingMiddleware"]
