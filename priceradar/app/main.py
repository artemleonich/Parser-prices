"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.router import router as api_router
from app.config import settings

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        (
            structlog.dev.ConsoleRenderer()
            if settings.DEBUG
            else structlog.processors.JSONRenderer()
        ),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        structlog.get_config()["wrapper_class"].log_level
        if hasattr(structlog.get_config().get("wrapper_class", object), "log_level")
        else 0
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

app = FastAPI(
    title="PriceRadar",
    description="Marketplace price monitoring service",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "priceradar"}


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup tasks."""
    logger.info("priceradar_started", debug=settings.DEBUG)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown tasks."""
    logger.info("priceradar_stopped")
