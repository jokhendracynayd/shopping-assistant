"""Structured API error definitions.

This module centralizes all error codes, default messages, and HTTP statuses.
Use `raise create_api_error(ErrorCode.XYZ, details=...)` to raise standardized errors.
"""

from enum import Enum
from typing import Any
from typing import TypedDict


class ErrorDef(TypedDict):
    message: str
    http_status: int
    numeric_code: int


class ErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    REQUEST_TOO_LARGE = "request_too_large"
    INTERNAL_ERROR = "internal_error"
    VECTORSTORE_ERROR = "vectorstore_error"
    LLM_ERROR = "llm_error"
    INGESTION_ERROR = "ingestion_error"


ERROR_REGISTRY: dict[ErrorCode, ErrorDef] = {
    ErrorCode.INVALID_INPUT: {
        "message": "Invalid input provided.",
        "http_status": 400,
        "numeric_code": 1001,
    },
    ErrorCode.NOT_FOUND: {
        "message": "Requested resource not found.",
        "http_status": 404,
        "numeric_code": 1002,
    },
    ErrorCode.UNAUTHORIZED: {
        "message": "Authentication credentials were not provided or are invalid.",
        "http_status": 401,
        "numeric_code": 1003,
    },
    ErrorCode.FORBIDDEN: {
        "message": "You do not have permission to perform this action.",
        "http_status": 403,
        "numeric_code": 1004,
    },
    ErrorCode.RATE_LIMIT_EXCEEDED: {
        "message": "Rate limit exceeded.",
        "http_status": 429,
        "numeric_code": 1005,
    },
    ErrorCode.REQUEST_TOO_LARGE: {
        "message": "Request body too large.",
        "http_status": 413,
        "numeric_code": 1006,
    },
    ErrorCode.INTERNAL_ERROR: {
        "message": "Internal server error.",
        "http_status": 500,
        "numeric_code": 1007,
    },
    ErrorCode.VECTORSTORE_ERROR: {
        "message": "Vector store error.",
        "http_status": 500,
        "numeric_code": 1008,
    },
    ErrorCode.LLM_ERROR: {
        "message": "Language model error.",
        "http_status": 502,
        "numeric_code": 1009,
    },
    ErrorCode.INGESTION_ERROR: {
        "message": "Document ingestion failed.",
        "http_status": 500,
        "numeric_code": 1010,
    },
}


class APIError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Any | None = None,
        http_status: int = 400,
        numeric_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.message = message
        self.details = details
        self.http_status = http_status
        self.numeric_code = numeric_code


def Error(code: ErrorCode, details: Any | None = None, message: str | None = None) -> APIError:
    """Factory to create an APIError using the registry defaults.

    The optional `message` overrides the default message in the registry.
    """
    if code not in ERROR_REGISTRY:
        reg = {"message": "Unknown error.", "http_status": 500}
    else:
        reg = ERROR_REGISTRY[code]
    msg = message or reg["message"]
    return APIError(
        code=code,
        message=msg,
        details=details,
        http_status=reg["http_status"],
        numeric_code=reg.get("numeric_code"),
    )


def to_error_dict(err: APIError) -> dict[str, Any]:
    return {
        "code": err.code,
        "numeric_code": getattr(err, "numeric_code", None),
        "message": err.message,
        "details": err.details,
    }
