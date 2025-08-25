import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import shopping
from app.middleware.rate_limiting import RateLimitingMiddleware
from app.middleware.request_size_limit import RequestSizeLimitMiddleware
from app.models.response import Response
from app.utils.errors import APIError
from app.utils.errors import to_error_dict
from app.utils.logger import get_logger
from app.utils.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    # Startup
    logger = get_logger("app.startup")
    logger.info("Application startup initiated")

    # Pre-warm Redis connection
    try:
        from app.database.redis_client import ping

        if await ping():
            logger.info("Redis connection established")
        else:
            logger.warning("Redis connection failed during startup")
    except Exception as e:
        logger.error(f"Redis initialization error: {e}")

    logger.info("Application startup completed")

    yield  # Application runs here

    # Shutdown
    logger = get_logger("app.shutdown")
    logger.info("Application shutdown initiated")

    # Close Redis connections
    try:
        from app.database.redis_client import close_redis_connections

        await close_redis_connections()
        logger.info("Redis connections closed")
    except Exception as e:
        logger.error(f"Error closing Redis connections: {e}")

    logger.info("Application shutdown completed")


def create_app() -> FastAPI:
    from app.config import settings

    setup_logging(
        enabled=settings.logging_enabled,
        level=getattr(__import__("logging"), settings.log_level.upper(), 20),
        log_dir=settings.log_dir,
    )
    logger = get_logger("app.startup")
    logger.info("starting application", extra={"logging_enabled": settings.logging_enabled})

    app = FastAPI(title="Shopping Assistant", lifespan=lifespan)

    # Add rate limiting middleware
    app.add_middleware(RateLimitingMiddleware, enabled=settings.rate_limiting_enabled)

    # Add request size limiting middleware
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_size_bytes=10 * 1024 * 1024,  # 10MB limit
        exclude_paths=["/health", "/docs", "/openapi.json"]
    )

    # Allow requests from local frontend during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # include API routers
    app.include_router(
        shopping.router,
        prefix="/api/v1/shopping",
        # , dependencies=[Depends(require_api_key)]
    )

    # register exception handler for APIError
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        logger = get_logger("app.errors")
        # log error with request context
        logger.error(
            f"APIError: {exc.code}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else None,
                "error": to_error_dict(exc),
            },
        )
        payload = Response(success=False, error=to_error_dict(exc))
        return JSONResponse(status_code=exc.http_status, content=payload.dict())

    # Application startup time for health checks
    app_start_time = time.time()

    async def check_redis_health() -> dict[str, Any]:
        """Check Redis service health."""
        try:
            from app.database.redis_client import get_redis_info

            redis_info = await get_redis_info()
            return {
                "service": "redis",
                "healthy": redis_info.get("connected", False),
                "details": redis_info,
            }
        except Exception as e:
            return {"service": "redis", "healthy": False, "error": str(e)}

    async def check_rag_service_health() -> dict[str, Any]:
        """Check RAG service health."""
        try:
            from app.services.rag_service import _rag_service

            # Check if retriever is initialized
            retriever_healthy = False
            if _rag_service.retriever:
                retriever_healthy = _rag_service.retriever.health_check()

            # Check if LLM client is configured
            llm_healthy = _rag_service.llm_client.is_configured()

            return {
                "service": "rag",
                "healthy": retriever_healthy and llm_healthy,
                "details": {
                    "retriever": retriever_healthy,
                    "llm_client": llm_healthy,
                },
            }
        except Exception as e:
            return {"service": "rag", "healthy": False, "error": str(e)}

    async def check_graph_service_health() -> dict[str, Any]:
        """Check LangGraph service health."""
        try:
            from app.graphs.shopping_graph import llm_client
            from app.graphs.shopping_graph import retriever

            # Check LLM client
            llm_healthy = llm_client.is_configured()

            # Check retriever if available
            retriever_healthy = True
            if retriever:
                retriever_healthy = retriever.health_check()

            return {
                "service": "graph",
                "healthy": llm_healthy and retriever_healthy,
                "details": {
                    "llm_client": llm_healthy,
                    "retriever": retriever_healthy,
                },
            }
        except Exception as e:
            return {"service": "graph", "healthy": False, "error": str(e)}

    @app.get("/health", tags=["Health"], summary="Basic health check")
    async def health_check():
        """
        Basic health check endpoint - returns 200 if application is running.

        This is a lightweight check that only verifies the application is responsive.
        Use /health/ready for comprehensive dependency checks.
        """
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "uptime_seconds": int(time.time() - app_start_time),
            "version": "0.1.0",
        }

    @app.get("/health/ready", tags=["Health"], summary="Readiness probe")
    async def readiness_check():
        """
        Comprehensive readiness check that verifies all dependencies.

        Returns 200 if all services are ready, 503 if any service is unavailable.
        Used by Kubernetes readiness probes and load balancers.
        """
        checks = []
        overall_healthy = True

        # Check Redis service
        redis_health = await check_redis_health()
        checks.append(redis_health)
        if not redis_health["healthy"]:
            overall_healthy = False

        # Check RAG service
        rag_health = await check_rag_service_health()
        checks.append(rag_health)
        if not rag_health["healthy"]:
            overall_healthy = False

        # Check Graph service
        graph_health = await check_graph_service_health()
        checks.append(graph_health)
        if not graph_health["healthy"]:
            overall_healthy = False

        response_data = {
            "status": "ready" if overall_healthy else "not_ready",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "uptime_seconds": int(time.time() - app_start_time),
            "services": checks,
        }

        status_code = 200 if overall_healthy else 503
        return JSONResponse(status_code=status_code, content=response_data)

    @app.get("/health/live", tags=["Health"], summary="Liveness probe")
    async def liveness_check():
        """
        Liveness probe endpoint for Kubernetes.

        Returns 200 if the application process is alive and responsive.
        Should only fail if the application needs to be restarted.
        """
        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "uptime_seconds": int(time.time() - app_start_time),
        }

    return app


app = create_app()
