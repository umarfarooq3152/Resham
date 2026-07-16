"""FastAPI application factory.

Unlike Dhaaga's `main.py`, there is no scheduler here — the crawl/index
cycle runs in a separate `resham.worker` process (see `worker/main.py`) so
a slow or failing crawl can never block or crash request handling.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from resham.api.rate_limit import limiter
from resham.config import get_settings
from resham.db.connection import close_db, get_session_maker, init_db
from resham.errors import ReshamException

logger = logging.getLogger(__name__)
settings = get_settings()
logging.getLogger("resham").setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Resham API starting")
    await init_db()
    yield
    await close_db()
    logger.info("Resham API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Resham",
        description="RAG search over a crawled catalog of Pakistani clothing brands",
        version="0.1.0",
        lifespan=lifespan,
    )

    extension_origins = [
        origin.strip() for origin in settings.extension_allowed_origins.split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, *extension_origins],
        allow_origin_regex=r"chrome-extension://[a-p]{32}",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-Device-Id"],
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "%s %s -> %s (%d ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-Duration-Ms"] = str(duration_ms)
        return response

    @app.exception_handler(ReshamException)
    async def resham_exception_handler(request: Request, exc: ReshamException):
        return JSONResponse(
            status_code=400,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception", extra={"path": request.url.path})
        if settings.debug:
            raise
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred",
                }
            },
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """Health check — verifies DB, Redis, and Chroma connectivity."""
        from redis.asyncio import from_url as redis_from_url

        health_status = {"status": "ok", "environment": settings.environment}

        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                await session.execute(text("SELECT 1"))
            health_status["database"] = "ok"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            health_status["database"] = f"error: {str(e)}"
            health_status["status"] = "degraded"

        try:
            redis_client = await redis_from_url(settings.redis_url)
            await redis_client.ping()
            await redis_client.close()
            health_status["cache"] = "ok"
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            health_status["cache"] = f"error: {str(e)}"
            health_status["status"] = "degraded"

        try:
            from resham.vectorstore.client import get_chroma_client

            get_chroma_client().heartbeat()
            health_status["vectorstore"] = "ok"
        except Exception as e:
            logger.error(f"Chroma health check failed: {e}")
            health_status["vectorstore"] = f"error: {str(e)}"
            health_status["status"] = "degraded"

        return health_status

    from resham.api.routers import (
        admin,
        auth,
        collections,
        devices,
        extension,
        session,
        voice,
        wishlist,
    )

    app.include_router(session.router)
    app.include_router(extension.router)
    app.include_router(voice.router)
    app.include_router(devices.router)
    app.include_router(auth.router)
    app.include_router(wishlist.router)
    app.include_router(collections.router)
    app.include_router(admin.router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "resham.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
