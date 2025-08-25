"""Standard response and error models for API endpoints."""

from typing import Any

from pydantic import BaseModel


class ErrorModel(BaseModel):
    code: str
    message: str
    details: Any | None = None
    numeric_code: int | None = None
    http_status: int | None = None
    timestamp: str | None = None


class Response(BaseModel):
    success: bool
    data: Any | None = None
    meta: dict | None = None
    error: ErrorModel | None = None
