"""REST API endpoints for tracked products."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session
from app.models.user import User
from app.services.price_service import PriceService

router = APIRouter()


@router.get("")
async def list_products(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List all tracked products for the current user."""
    svc = PriceService(session)
    products = await svc.get_user_products(user.id)
    return [
        {
            "id": p.id,
            "marketplace": p.marketplace.value,
            "external_id": p.external_id,
            "url": p.url,
            "title": p.title,
            "current_price": str(p.current_price) if p.current_price else None,
            "previous_price": str(p.previous_price) if p.previous_price else None,
            "price_updated_at": p.price_updated_at.isoformat() if p.price_updated_at else None,
            "image_url": p.image_url,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat(),
        }
        for p in products
    ]


@router.post("")
async def add_product(
    data: dict,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Add a new product to track by URL."""
    url = data.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    svc = PriceService(session)
    try:
        product = await svc.add_product(user, url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": product.id,
        "marketplace": product.marketplace.value,
        "title": product.title,
        "current_price": str(product.current_price) if product.current_price else None,
        "url": product.url,
    }


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete a tracked product."""
    svc = PriceService(session)
    deleted = await svc.delete_product(product_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "deleted"}


@router.get("/{product_id}/history")
async def product_history(
    product_id: int,
    days: int = 30,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Get price history for a product."""
    svc = PriceService(session)
    product = await svc.get_product_by_id(product_id)
    if product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="Product not found")

    history = await svc.get_price_history(product_id, days)
    return [
        {
            "price": str(h.price),
            "original_price": str(h.original_price) if h.original_price else None,
            "discount_percent": h.discount_percent,
            "in_stock": h.in_stock,
            "recorded_at": h.recorded_at.isoformat(),
        }
        for h in history
    ]
