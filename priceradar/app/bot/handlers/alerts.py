"""Handlers for alert rule management."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards import alert_type_keyboard, back_to_menu_keyboard, main_menu_keyboard
from app.database import async_session_factory
from app.models.alert import AlertRule, RuleType
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.price_service import PriceService
from app.services.subscription_service import SubscriptionService

logger = structlog.get_logger()

router = Router(name="alerts")


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class AlertStates(StatesGroup):
    """FSM states for custom-price alert creation."""

    waiting_for_price = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RULE_TYPE_LABELS: dict[RuleType, str] = {
    RuleType.PRICE_DROP: "\U0001f4c9 \u0421\u043d\u0438\u0436\u0435\u043d\u0438\u0435 \u0446\u0435\u043d\u044b",
    RuleType.PRICE_RISE: "\U0001f4c8 \u0420\u043e\u0441\u0442 \u0446\u0435\u043d\u044b",
    RuleType.PRICE_BELOW: "\u2b07\ufe0f \u0426\u0435\u043d\u0430 \u043d\u0438\u0436\u0435",
    RuleType.PRICE_ABOVE: "\u2b06\ufe0f \u0426\u0435\u043d\u0430 \u0432\u044b\u0448\u0435",
    RuleType.BACK_IN_STOCK: "\U0001f4e6 \u041f\u043e\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
}


def _fmt_price(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.0f} \u20bd".replace(",", "\u202f")


def _format_rule(rule: AlertRule) -> str:
    """Format a single alert rule for display."""
    label = RULE_TYPE_LABELS.get(rule.rule_type, rule.rule_type.value)
    threshold = ""
    if rule.threshold_value is not None:
        threshold = f" ({_fmt_price(rule.threshold_value)})"
    status = "\u2705" if rule.is_active else "\u274c"
    return f"{status} {label}{threshold}"


# ---------------------------------------------------------------------------
# Show current alerts
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "alerts_settings")
async def cb_alerts_settings(callback: CallbackQuery) -> None:
    """Show the user's current alert rules."""
    if callback.from_user is None:
        return

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )

        alert_svc = AlertService(session)
        rules = await alert_svc.get_user_alert_rules(user.id, active_only=False)

        # Also load product titles for context
        price_svc = PriceService(session)
        products_map: dict[int, str] = {}
        for rule in rules:
            if rule.product_id and rule.product_id not in products_map:
                product = await price_svc.get_product_by_id(rule.product_id)
                if product:
                    products_map[rule.product_id] = product.title

    if not rules:
        await callback.message.edit_text(
            "\U0001f514 \u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0430\u043b\u0435\u0440\u0442\u043e\u0432.\n\n"
            "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0442\u043e\u0432\u0430\u0440 \u0438 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 "
            "\u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f \u043e \u0446\u0435\u043d\u0435.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = ["\U0001f514 <b>\u0412\u0430\u0448\u0438 \u0430\u043b\u0435\u0440\u0442\u044b:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []

    for rule in rules:
        product_title = products_map.get(rule.product_id, "\u0412\u0441\u0435 \u0442\u043e\u0432\u0430\u0440\u044b") if rule.product_id else "\u0412\u0441\u0435 \u0442\u043e\u0432\u0430\u0440\u044b"
        lines.append(f"\u2022 {_format_rule(rule)}")
        lines.append(f"  \U0001f4e6 {product_title}\n")
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0430\u043b\u0435\u0440\u0442 #{rule.id}",
                    callback_data=f"delete_alert:{rule.id}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="\U0001f3e0 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="main_menu")]
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Add alert from product detail
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("add_alert:"))
async def cb_add_alert(callback: CallbackQuery) -> None:
    """Show alert type selection for a product."""
    product_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "\U0001f514 \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u0438\u043f \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f:",
        reply_markup=alert_type_keyboard(product_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Alert type: price drop
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("alert_drop:"))
async def cb_alert_drop(callback: CallbackQuery) -> None:
    """Create a price-drop alert rule for the product."""
    if callback.from_user is None:
        return

    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )

        alert_svc = AlertService(session)
        await alert_svc.create_alert_rule(
            user_id=user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=product_id,
        )
        await session.commit()

    await callback.message.edit_text(
        "\u2705 \u0410\u043b\u0435\u0440\u0442 \u043d\u0430 <b>\u0441\u043d\u0438\u0436\u0435\u043d\u0438\u0435 \u0446\u0435\u043d\u044b</b> \u0441\u043e\u0437\u0434\u0430\u043d!\n\n"
        "\u0412\u044b \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435, "
        "\u043a\u043e\u0433\u0434\u0430 \u0446\u0435\u043d\u0430 \u0441\u043d\u0438\u0437\u0438\u0442\u0441\u044f.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Alert type: back in stock
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("alert_stock:"))
async def cb_alert_stock(callback: CallbackQuery) -> None:
    """Create a back-in-stock alert rule for the product."""
    if callback.from_user is None:
        return

    product_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )

        alert_svc = AlertService(session)
        await alert_svc.create_alert_rule(
            user_id=user.id,
            rule_type=RuleType.BACK_IN_STOCK,
            product_id=product_id,
        )
        await session.commit()

    await callback.message.edit_text(
        "\u2705 \u0410\u043b\u0435\u0440\u0442 \u043d\u0430 <b>\u043f\u043e\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438</b> \u0441\u043e\u0437\u0434\u0430\u043d!\n\n"
        "\u0412\u044b \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435, "
        "\u043a\u043e\u0433\u0434\u0430 \u0442\u043e\u0432\u0430\u0440 \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Alert type: custom price (step 1 - ask for price)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("alert_custom:"))
async def cb_alert_custom(callback: CallbackQuery, state: FSMContext) -> None:
    """Ask user to enter target price for the alert."""
    product_id = int(callback.data.split(":")[1])

    await state.set_state(AlertStates.waiting_for_price)
    await state.update_data(alert_product_id=product_id)

    await callback.message.edit_text(
        "\u270f\ufe0f \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0436\u0435\u043b\u0430\u0435\u043c\u0443\u044e \u0446\u0435\u043d\u0443 \u0432 \u0440\u0443\u0431\u043b\u044f\u0445.\n\n"
        "\u041a\u043e\u0433\u0434\u0430 \u0446\u0435\u043d\u0430 \u0441\u0442\u0430\u043d\u0435\u0442 \u043d\u0438\u0436\u0435 "
        "\u044d\u0442\u043e\u0433\u043e \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f, \u0432\u044b \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Alert type: custom price (step 2 - receive price)
# ---------------------------------------------------------------------------

@router.message(AlertStates.waiting_for_price)
async def msg_custom_price(message: Message, state: FSMContext) -> None:
    """Receive the target price and create PRICE_BELOW alert."""
    if message.from_user is None or not message.text:
        return

    raw = message.text.strip().replace(",", ".").replace("\u202f", "").replace(" ", "")

    try:
        price = Decimal(raw)
        if price <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(
            "\u274c \u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, "
            "\u0432\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u0443\u044e \u0446\u0435\u043d\u0443 "
            "(\u043f\u043e\u043b\u043e\u0436\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0435 \u0447\u0438\u0441\u043b\u043e).",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    product_id: int = data["alert_product_id"]

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            username=message.from_user.username,
        )

        alert_svc = AlertService(session)
        await alert_svc.create_alert_rule(
            user_id=user.id,
            rule_type=RuleType.PRICE_BELOW,
            product_id=product_id,
            threshold_value=price,
        )
        await session.commit()

    await state.clear()

    await message.answer(
        f"\u2705 \u0410\u043b\u0435\u0440\u0442 \u0441\u043e\u0437\u0434\u0430\u043d!\n\n"
        f"\u0412\u044b \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0435 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435, "
        f"\u043a\u043e\u0433\u0434\u0430 \u0446\u0435\u043d\u0430 \u0441\u0442\u0430\u043d\u0435\u0442 \u043d\u0438\u0436\u0435 {_fmt_price(price)}.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Delete alert
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("delete_alert:"))
async def cb_delete_alert(callback: CallbackQuery) -> None:
    """Delete an alert rule."""
    if callback.from_user is None:
        return

    rule_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )

        alert_svc = AlertService(session)
        deleted = await alert_svc.delete_alert_rule(rule_id, user.id)
        if deleted:
            await session.commit()
        else:
            await session.rollback()

    if deleted:
        await callback.message.edit_text(
            "\u2705 \u0410\u043b\u0435\u0440\u0442 \u0443\u0434\u0430\u043b\u0451\u043d.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0430\u043b\u0435\u0440\u0442.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()
