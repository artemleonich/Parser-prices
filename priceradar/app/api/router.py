"""Main API router combining all sub-routers."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.products import router as products_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(products_router, prefix="/api/products", tags=["products"])
router.include_router(dashboard_router, tags=["dashboard"])
