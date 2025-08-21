"""Standard response and error models for API endpoints."""
from typing import Any, Optional
from pydantic import BaseModel


class ErrorModel(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
    numeric_code: Optional[int] = None
    http_status: Optional[int] = None
    timestamp: Optional[str] = None


class Response(BaseModel):
    success: bool
    data: Optional[Any] = None
    meta: Optional[dict] = None
    error: Optional[ErrorModel] = None


