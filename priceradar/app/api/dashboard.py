from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session
from app.models.user import PLAN_LIMITS, User
from app.services.price_service import PriceService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    svc = PriceService(session)
    products = await svc.get_user_products(user.id)
    product_count = len(products)
    limits = PLAN_LIMITS[user.subscription_plan]

    product_data = []
    for p in products:
        trend = await svc.get_price_trend(p.id, days=7)
        product_data.append({
            "product": p,
            "trend": trend,
            "trend_arrow": _trend_arrow(trend),
        })

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "products": product_data,
            "product_count": product_count,
            "max_products": limits["max_products"],
            "plan": user.subscription_plan.value,
        },
    )


@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(
    request: Request,
    product_id: int,
    days: int = 30,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    svc = PriceService(session)
    product = await svc.get_product_by_id(product_id)

    if product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="Product not found")

    history = await svc.get_price_history(product_id, days)
    min_price = await svc.get_min_price(product_id, days)
    trend = await svc.get_price_trend(product_id, days=7)

    chart_labels = [h.recorded_at.strftime("%d.%m %H:%M") for h in history]
    chart_prices = [float(h.price) for h in history]
    chart_original = [float(h.original_price) if h.original_price else None for h in history]

    return templates.TemplateResponse(
        "product_detail.html",
        {
            "request": request,
            "user": user,
            "product": product,
            "history": history,
            "min_price": min_price,
            "trend": trend,
            "trend_arrow": _trend_arrow(trend),
            "chart_labels": chart_labels,
            "chart_prices": chart_prices,
            "chart_original": chart_original,
            "days": days,
        },
    )


@router.get("/dashboard/products-table", response_class=HTMLResponse)
async def products_table_partial(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    svc = PriceService(session)
    products = await svc.get_user_products(user.id)

    product_data = []
    for p in products:
        trend = await svc.get_price_trend(p.id, days=7)
        product_data.append({
            "product": p,
            "trend": trend,
            "trend_arrow": _trend_arrow(trend),
        })

    return templates.TemplateResponse(
        "components/product_card.html",
        {
            "request": request,
            "products": product_data,
        },
    )


def _trend_arrow(trend: float | None) -> str:
    if trend is None:
        return "\u2192"
    if trend > 1:
        return "\u2191"
    if trend < -1:
        return "\u2193"
    return "\u2192"
