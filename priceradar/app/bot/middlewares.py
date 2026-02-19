"""Middleware for the PriceRadar Telegram bot.

Responsibilities:
- Ensure every incoming update has a corresponding User row in the database.
- Simple in-memory rate limiting per Telegram user.
- Check subscription expiration and auto-downgrade if necessary.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.database import async_session_factory
from app.services.subscription_service import SubscriptionService

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Rate-limit settings
# ---------------------------------------------------------------------------
RATE_LIMIT_WINDOW: float = 1.0  # seconds
MAX_REQUESTS_PER_WINDOW: int = 5


class ThrottleMiddleware(BaseMiddleware):
    """Outer middleware: simple per-user rate limiter (in-memory).

    Drops updates that exceed *MAX_REQUESTS_PER_WINDOW* within
    *RATE_LIMIT_WINDOW* seconds.
    """

    def __init__(self) -> None:
        super().__init__()
        # user_id -> list of timestamps
        self._timestamps: Dict[int, list[float]] = defaultdict(list)

    def _is_rate_limited(self, user_id: int) -> bool:
        """Return True if the user has exceeded the rate limit."""
        now = time.monotonic()
        window_start = now - RATE_LIMIT_WINDOW
        # Drop old entries
        self._timestamps[user_id] = [
            ts for ts in self._timestamps[user_id] if ts > window_start
        ]
        if len(self._timestamps[user_id]) >= MAX_REQUESTS_PER_WINDOW:
            return True
        self._timestamps[user_id].append(now)
        return False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Extract user from the event
        user_tg = data.get("event_from_user")
        if user_tg is not None and self._is_rate_limited(user_tg.id):
            logger.warning("rate_limited", telegram_id=user_tg.id)
            # Silently drop the update
            return None

        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Inner middleware: ensure the user exists in DB and inject into handler data.

    Also checks subscription expiration and downgrades if needed.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_tg = data.get("event_from_user")
        if user_tg is None:
            # Non-user updates (channel posts, etc.) -- pass through
            return await handler(event, data)

        async with async_session_factory() as session:
            svc = SubscriptionService(session)

            user = await svc.get_or_create_user(
                telegram_id=user_tg.id,
                first_name=user_tg.first_name or "",
                username=user_tg.username,
            )

            # Check subscription status
            await svc.check_and_downgrade_expired(user)

            await session.commit()

            # Inject the DB user object into handler data
            data["db_user"] = user

        return await handler(event, data)
