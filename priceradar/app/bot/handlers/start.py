from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu_keyboard
from app.database import async_session_factory
from app.models.user import User
from app.services.subscription_service import SubscriptionService

logger = structlog.get_logger()

router = Router(name="start")

WELCOME_TEXT: str = (
    "\U0001f4e1 <b>PriceRadar</b> \u2014 \u0432\u0430\u0448 \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a "
    "\u043f\u043e \u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u043d\u0438\u044e \u0446\u0435\u043d!\n\n"
    "\u0414\u043e\u0431\u0430\u0432\u043b\u044f\u0439\u0442\u0435 \u0442\u043e\u0432\u0430\u0440\u044b "
    "\u0441 Wildberries, Ozon \u0438 \u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0430\u0440\u043a\u0435\u0442, "
    "\u0438 \u0431\u043e\u0442 \u0431\u0443\u0434\u0435\u0442 \u0441\u043b\u0435\u0434\u0438\u0442\u044c "
    "\u0437\u0430 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435\u043c \u0446\u0435\u043d "
    "\u0438 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u044f\u0442\u044c \u0432\u0430\u0441.\n\n"
    "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435:"
)

HELP_TEXT: str = (
    "\u2753 <b>\u041f\u043e\u043c\u043e\u0449\u044c</b>\n\n"
    "\U0001f50d <b>\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u043e\u0432\u0430\u0440</b> \u2014 "
    "\u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u0442\u043e\u0432\u0430\u0440, "
    "\u0438 \u0431\u043e\u0442 \u043d\u0430\u0447\u043d\u0451\u0442 \u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u0442\u044c \u0446\u0435\u043d\u0443.\n\n"
    "\U0001f4ca <b>\u041c\u043e\u0438 \u0442\u043e\u0432\u0430\u0440\u044b</b> \u2014 "
    "\u0441\u043f\u0438\u0441\u043e\u043a \u0432\u0441\u0435\u0445 \u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0445 "
    "\u0442\u043e\u0432\u0430\u0440\u043e\u0432 \u0441 \u0442\u0435\u043a\u0443\u0449\u0438\u043c\u0438 \u0446\u0435\u043d\u0430\u043c\u0438.\n\n"
    "\U0001f514 <b>\u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0430\u043b\u0435\u0440\u0442\u044b</b> \u2014 "
    "\u0441\u043e\u0437\u0434\u0430\u0439\u0442\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u0430 \u0434\u043b\u044f \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0439: "
    "\u0441\u043d\u0438\u0436\u0435\u043d\u0438\u0435 \u0446\u0435\u043d\u044b, "
    "\u043f\u043e\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438 "
    "\u0438\u043b\u0438 \u0434\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u0435 \u0436\u0435\u043b\u0430\u0435\u043c\u043e\u0439 \u0446\u0435\u043d\u044b.\n\n"
    "\U0001f4b3 <b>\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430</b> \u2014 "
    "\u0443\u043b\u0443\u0447\u0448\u0438\u0442\u0435 \u0442\u0430\u0440\u0438\u0444 \u0434\u043b\u044f "
    "\u0431\u043e\u043b\u044c\u0448\u0435\u0433\u043e \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u0430 "
    "\u0442\u043e\u0432\u0430\u0440\u043e\u0432 \u0438 \u0430\u043b\u0435\u0440\u0442\u043e\u0432.\n\n"
    "\U0001f3ea <b>\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0435 \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u044b:</b>\n"
    "\u2022 Wildberries\n"
    "\u2022 Ozon\n"
    "\u2022 \u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0430\u0440\u043a\u0435\u0442"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        svc = SubscriptionService(session)
        user: User = await svc.get_or_create_user(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            username=message.from_user.username,
        )
        await session.commit()

    logger.info(
        "start_command",
        telegram_id=message.from_user.id,
        user_id=user.id,
    )

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        HELP_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
