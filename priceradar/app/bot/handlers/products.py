from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    PRODUCTS_PER_PAGE,
    alert_type_keyboard,
    back_to_menu_keyboard,
    confirm_delete_keyboard,
    main_menu_keyboard,
    product_actions_keyboard,
    products_pagination_keyboard,
)
from app.database import async_session_factory
from app.models.user import User
from app.services.price_service import PriceService

logger = structlog.get_logger()

router = Router(name="products")


class AddProductStates(StatesGroup):
    waiting_for_url = State()


def _fmt_price(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.0f} \u20bd".replace(",", "\u202f")


def _trend_arrow(trend: float | None) -> str:
    if trend is None:
        return "\u2014"
    if trend > 0:
        return f"\u2191 +{trend:.1f}%"
    if trend < 0:
        return f"\u2193 {trend:.1f}%"
    return "\u2194 0%"


MARKETPLACE_LABELS: dict[str, str] = {
    "wildberries": "Wildberries",
    "ozon": "Ozon",
    "yandex_market": "\u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0430\u0440\u043a\u0435\u0442",
}


@router.callback_query(F.data == "add_product")
async def cb_add_product(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddProductStates.waiting_for_url)
    await callback.message.edit_text(
        "\U0001f517 \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 "
        "\u043d\u0430 \u0442\u043e\u0432\u0430\u0440 \u0441 Wildberries, Ozon "
        "\u0438\u043b\u0438 \u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0430\u0440\u043a\u0435\u0442.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddProductStates.waiting_for_url)
async def msg_product_url(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return

    url = message.text.strip()

    if not url.startswith("http"):
        await message.answer(
            "\u274c \u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, "
            "\u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u0443\u044e "
            "\u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u0442\u043e\u0432\u0430\u0440 "
            "(\u043d\u0430\u0447\u0438\u043d\u0430\u044e\u0449\u0443\u044e\u0441\u044f \u0441 http).",
            parse_mode="HTML",
        )
        return

    processing_msg = await message.answer(
        "\u23f3 \u041e\u0431\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u044e \u0441\u0441\u044b\u043b\u043a\u0443\u2026",
        parse_mode="HTML",
    )

    async with async_session_factory() as session:
        from app.services.subscription_service import SubscriptionService

        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            username=message.from_user.username,
        )

        price_svc = PriceService(session)

        try:
            product = await price_svc.add_product(user, url)
            await session.commit()
        except ValueError as exc:
            await session.rollback()
            await processing_msg.edit_text(
                f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {exc}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            await state.clear()
            return
        except Exception:
            await session.rollback()
            logger.exception("add_product_error", url=url)
            await processing_msg.edit_text(
                "\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c "
                "\u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u043e\u0432\u0430\u0440. "
                "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435.",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            await state.clear()
            return

    await state.clear()

    text = (
        "\u2705 <b>\u0422\u043e\u0432\u0430\u0440 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!</b>\n\n"
        f"\U0001f4e6 {product.title}\n"
        f"\U0001f4b0 \u0426\u0435\u043d\u0430: {_fmt_price(product.current_price)}\n\n"
        "\U0001f514 \u0425\u043e\u0442\u0438\u0442\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c "
        "\u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435 \u043e:"
    )

    await processing_msg.edit_text(
        text,
        reply_markup=alert_type_keyboard(product.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "my_products")
async def cb_my_products(callback: CallbackQuery) -> None:
    await _show_products_page(callback, page=0)


@router.callback_query(F.data.startswith("products_page:"))
async def cb_products_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    await _show_products_page(callback, page=page)


async def _show_products_page(callback: CallbackQuery, page: int) -> None:
    if callback.from_user is None:
        return

    async with async_session_factory() as session:
        from app.services.subscription_service import SubscriptionService

        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )

        price_svc = PriceService(session)
        products = await price_svc.get_user_products(user.id)

    if not products:
        await callback.message.edit_text(
            "\U0001f4e6 \u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 "
            "\u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0445 \u0442\u043e\u0432\u0430\u0440\u043e\u0432.\n"
            "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u043e\u0432\u0430\u0440\u00bb, "
            "\u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    total_pages = max(1, math.ceil(len(products) / PRODUCTS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    text = (
        f"\U0001f4ca <b>\u041c\u043e\u0438 \u0442\u043e\u0432\u0430\u0440\u044b</b> "
        f"(\u0441\u0442\u0440. {page + 1}/{total_pages})\n\n"
        f"\u0412\u0441\u0435\u0433\u043e \u0442\u043e\u0432\u0430\u0440\u043e\u0432: {len(products)}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=products_pagination_keyboard(products, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("product_detail:"))
async def cb_product_detail(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        price_svc = PriceService(session)
        product = await price_svc.get_product_by_id(product_id)

        if product is None:
            await callback.message.edit_text(
                "\u274c \u0422\u043e\u0432\u0430\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            await callback.answer()
            return

        trend = await price_svc.get_price_trend(product_id, days=7)
        min_price = await price_svc.get_min_price(product_id, days=30)

    mp_label = MARKETPLACE_LABELS.get(product.marketplace.value, product.marketplace.value)

    lines = [
        f"\U0001f4e6 <b>{product.title}</b>\n",
        f"\U0001f3ea \u041c\u0430\u0440\u043a\u0435\u0442\u043f\u043b\u0435\u0439\u0441: {mp_label}",
        f"\U0001f4b0 \u0422\u0435\u043a\u0443\u0449\u0430\u044f \u0446\u0435\u043d\u0430: {_fmt_price(product.current_price)}",
    ]

    if product.previous_price is not None:
        lines.append(
            f"\U0001f4c9 \u041f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0430\u044f: {_fmt_price(product.previous_price)}"
        )

    lines.append(f"\U0001f4c8 \u0422\u0440\u0435\u043d\u0434 (7 \u0434\u043d.): {_trend_arrow(trend)}")

    if min_price is not None:
        lines.append(
            f"\U0001f4ca \u041c\u0438\u043d. \u0437\u0430 30 \u0434\u043d.: {_fmt_price(min_price)}"
        )

    if product.url:
        lines.append(f"\n\U0001f517 <a href=\"{product.url}\">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 \u0441\u0430\u0439\u0442\u0435</a>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=product_actions_keyboard(product_id),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("price_history:"))
async def cb_price_history(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        price_svc = PriceService(session)
        product = await price_svc.get_product_by_id(product_id)
        if product is None:
            await callback.answer("\u0422\u043e\u0432\u0430\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
            return

        history = await price_svc.get_price_history(product_id, days=30)

    if not history:
        await callback.answer(
            "\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0446\u0435\u043d \u043f\u0443\u0441\u0442\u0430",
            show_alert=True,
        )
        return

    lines = [f"\U0001f4c8 <b>\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0446\u0435\u043d (30 \u0434\u043d.)</b>\n"]
    lines.append(f"\U0001f4e6 {product.title}\n")

    for record in history[-10:]:
        date_str = record.recorded_at.strftime("%d.%m %H:%M")
        stock = "\u2705" if record.in_stock else "\u274c"
        lines.append(f"{date_str} \u2014 {_fmt_price(record.price)} {stock}")

    if len(history) > 10:
        lines.append(f"\n\u2026 \u0438 \u0435\u0449\u0451 {len(history) - 10} \u0437\u0430\u043f\u0438\u0441\u0435\u0439")

    from app.bot.keyboards import back_to_menu_keyboard as _back
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data=f"product_detail:{product_id}")],
            [InlineKeyboardButton(text="\U0001f3e0 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="main_menu")],
        ]
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("refresh_price:"))
async def cb_refresh_price(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        price_svc = PriceService(session)
        product = await price_svc.get_product_by_id(product_id)
        if product is None:
            await callback.answer("\u0422\u043e\u0432\u0430\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
            return

        try:
            from app.parsers import PARSERS
            parser_cls = PARSERS.get(product.marketplace.value)
            if parser_cls is None:
                await callback.answer(
                    "\u041f\u0430\u0440\u0441\u0435\u0440 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d",
                    show_alert=True,
                )
                return

            parser = parser_cls()
            parsed = await parser.parse_product(product.url)
            await price_svc.update_product_price(product, parsed)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("refresh_price_error", product_id=product_id)
            await callback.answer(
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0446\u0435\u043d\u0443",
                show_alert=True,
            )
            return

    await callback.answer(
        "\u2705 \u0426\u0435\u043d\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430!",
        show_alert=True,
    )
    callback.data = f"product_detail:{product_id}"
    await cb_product_detail(callback)


@router.callback_query(F.data.startswith("delete_product:"))
async def cb_delete_product(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        price_svc = PriceService(session)
        product = await price_svc.get_product_by_id(product_id)

    if product is None:
        await callback.answer("\u0422\u043e\u0432\u0430\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    await callback.message.edit_text(
        f"\U0001f5d1 \u0412\u044b \u0443\u0432\u0435\u0440\u0435\u043d\u044b, "
        f"\u0447\u0442\u043e \u0445\u043e\u0442\u0438\u0442\u0435 \u0443\u0434\u0430\u043b\u0438\u0442\u044c "
        f"\u0442\u043e\u0432\u0430\u0440 <b>{product.title}</b>?",
        reply_markup=confirm_delete_keyboard(product_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        from app.services.subscription_service import SubscriptionService

        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )

        price_svc = PriceService(session)
        deleted = await price_svc.delete_product(product_id, user.id)
        if deleted:
            await session.commit()
        else:
            await session.rollback()

    if deleted:
        await callback.message.edit_text(
            "\u2705 \u0422\u043e\u0432\u0430\u0440 \u0443\u0434\u0430\u043b\u0451\u043d.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0442\u043e\u0432\u0430\u0440.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()
