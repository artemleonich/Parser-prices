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

RATE_LIMIT_WINDOW: float = 1.0  # seconds
MAX_REQUESTS_PER_WINDOW: int = 5


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._timestamps: Dict[int, list[float]] = defaultdict(list)

    def _is_rate_limited(self, user_id: int) -> bool:
        now = time.monotonic()
        window_start = now - RATE_LIMIT_WINDOW
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
        user_tg = data.get("event_from_user")
        if user_tg is not None and self._is_rate_limited(user_tg.id):
            logger.warning("rate_limited", telegram_id=user_tg.id)
            return None

        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_tg = data.get("event_from_user")
        if user_tg is None:
            return await handler(event, data)

        async with async_session_factory() as session:
            svc = SubscriptionService(session)

            user = await svc.get_or_create_user(
                telegram_id=user_tg.id,
                first_name=user_tg.first_name or "",
                username=user_tg.username,
            )

            await svc.check_and_downgrade_expired(user)
            await session.commit()

            data["db_user"] = user

        return await handler(event, data)
