from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import shopping
from app.utils.errors import APIError, to_error_dict, ErrorCode, Error
from app.utils.security import require_api_key
from fastapi import Depends
from app.utils.logger import setup_logging, get_logger
from app.models.response import Response


def create_app() -> FastAPI:
    from app.config import settings

    setup_logging(enabled=settings.logging_enabled, level=getattr(__import__("logging"), settings.log_level.upper(), 20), log_dir=settings.log_dir)
    logger = get_logger("app.startup")
    logger.info("starting application", extra={"logging_enabled": settings.logging_enabled})

    app = FastAPI(title="Shopping Assistant")

    # include API routers
    app.include_router(
        shopping.router, prefix="/api/v1/shopping"
        # , dependencies=[Depends(require_api_key)]
    )

    # register exception handler for APIError
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        logger = get_logger("app.errors")
        # log error with request context
        logger.error(
            f"APIError: {exc.code}", extra={
                "path": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else None,
                "error": to_error_dict(exc),
            },
        )
        payload = Response(success=False, error=to_error_dict(exc))
        return JSONResponse(status_code=exc.http_status, content=payload.dict())

    return app


app = create_app()
