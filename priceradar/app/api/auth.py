"""Telegram Login Widget authentication."""

import hashlib
import hmac
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.services.subscription_service import SubscriptionService

logger = structlog.get_logger()

router = APIRouter()


def verify_telegram_auth(data: dict) -> bool:
    """Verify data received from Telegram Login Widget.

    Uses HMAC-SHA256 with bot token hash as the secret key.
    """
    check_hash = data.pop("hash", None)
    if not check_hash:
        return False

    # Sort and concatenate data
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items()) if v is not None
    )

    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, check_hash):
        return False

    # Check auth_date is not too old (1 day max)
    auth_date = int(data.get("auth_date", 0))
    now = int(datetime.now(timezone.utc).timestamp())
    if now - auth_date > 86400:
        return False

    return True


@router.get("/telegram")
async def telegram_auth(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Handle Telegram Login Widget callback."""
    params = dict(request.query_params)

    if not verify_telegram_auth(params.copy()):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth data")

    telegram_id = int(params["id"])
    first_name = params.get("first_name", "User")
    username = params.get("username")

    svc = SubscriptionService(session)
    user = await svc.get_or_create_user(telegram_id, first_name, username)

    # Set session cookie (simple approach for MVP)
    response.set_cookie(
        key="user_id",
        value=str(user.id),
        httponly=True,
        max_age=86400 * 30,
        samesite="lax",
    )

    logger.info("user_authenticated", telegram_id=telegram_id, user_id=user.id)
    return {"status": "ok", "redirect": "/dashboard"}


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> "User":  # noqa: F821
    """Dependency to get the current authenticated user from cookie."""
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from app.models.user import User

    user = await session.get(User, int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user
