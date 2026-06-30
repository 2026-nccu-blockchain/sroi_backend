"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application.
    """

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    app.include_router(health_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
