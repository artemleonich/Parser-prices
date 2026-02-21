from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers.alerts import router as alerts_router
from app.bot.handlers.products import router as products_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.subscription import router as subscription_router
from app.bot.middlewares import ThrottleMiddleware, UserMiddleware
from app.config import settings

logger = structlog.get_logger()


async def main() -> None:
    logger.info("bot_starting", bot_username=settings.TELEGRAM_BOT_USERNAME)

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # ThrottleMiddleware runs first to drop spam before any DB access
    dp.message.middleware(ThrottleMiddleware())
    dp.callback_query.middleware(ThrottleMiddleware())
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(start_router)
    dp.include_router(products_router)
    dp.include_router(alerts_router)
    dp.include_router(subscription_router)

    try:
        logger.info("bot_polling_started")
        await dp.start_polling(bot)
    finally:
        logger.info("bot_stopped")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
