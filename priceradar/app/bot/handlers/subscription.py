"""Handlers for subscription management and Telegram Payments (YooKassa)."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.bot.keyboards import main_menu_keyboard, subscription_keyboard
from app.config import settings
from app.database import async_session_factory
from app.models.user import PLAN_LIMITS, SubscriptionPlan, User
from app.services.subscription_service import PLAN_PRICES, SubscriptionService

logger = structlog.get_logger()

router = Router(name="subscription")


# ---------------------------------------------------------------------------
# Plan description helpers
# ---------------------------------------------------------------------------

PLAN_NAMES: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.FREE: "Free",
    SubscriptionPlan.BASIC: "Basic",
    SubscriptionPlan.PRO: "Pro",
}

PLAN_DESCRIPTIONS: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.BASIC: (
        "\u2b50 <b>Basic</b> \u2014 990 \u20bd/\u043c\u0435\u0441\n"
        "\u2022 \u0414\u043e 50 \u0442\u043e\u0432\u0430\u0440\u043e\u0432\n"
        "\u2022 20 \u0430\u043b\u0435\u0440\u0442\u043e\u0432\n"
        "\u2022 3 \u043c\u0430\u0440\u043a\u0435\u0442\u043f\u043b\u0435\u0439\u0441\u0430\n"
        "\u2022 \u0418\u0441\u0442\u043e\u0440\u0438\u044f 30 \u0434\u043d\u0435\u0439\n"
        "\u2022 \u042d\u043a\u0441\u043f\u043e\u0440\u0442 CSV"
    ),
    SubscriptionPlan.PRO: (
        "\U0001f451 <b>Pro</b> \u2014 2 490 \u20bd/\u043c\u0435\u0441\n"
        "\u2022 \u0414\u043e 200 \u0442\u043e\u0432\u0430\u0440\u043e\u0432\n"
        "\u2022 \u0411\u0435\u0437\u043b\u0438\u043c\u0438\u0442 \u0430\u043b\u0435\u0440\u0442\u043e\u0432\n"
        "\u2022 3 \u043c\u0430\u0440\u043a\u0435\u0442\u043f\u043b\u0435\u0439\u0441\u0430\n"
        "\u2022 \u0418\u0441\u0442\u043e\u0440\u0438\u044f 90 \u0434\u043d\u0435\u0439\n"
        "\u2022 \u042d\u043a\u0441\u043f\u043e\u0440\u0442 CSV"
    ),
}


# ---------------------------------------------------------------------------
# Show current subscription
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "subscription")
async def cb_subscription(callback: CallbackQuery) -> None:
    """Show current subscription status and upgrade options."""
    if callback.from_user is None:
        return

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "",
            username=callback.from_user.username,
        )
        info_text = sub_svc.format_subscription_info(user)

    text = (
        f"{info_text}\n\n"
        "\u2b06\ufe0f \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u0430\u0440\u0438\u0444 \u0434\u043b\u044f \u043e\u043f\u043b\u0430\u0442\u044b:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=subscription_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Plan selection -> send invoice
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("subscribe:"))
async def cb_subscribe(callback: CallbackQuery) -> None:
    """Send a Telegram payment invoice for the selected plan."""
    if callback.from_user is None:
        return

    plan_key = callback.data.split(":")[1]
    try:
        plan = SubscriptionPlan(plan_key)
    except ValueError:
        await callback.answer(
            "\u274c \u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0442\u0430\u0440\u0438\u0444",
            show_alert=True,
        )
        return

    if plan not in PLAN_PRICES:
        await callback.answer(
            "\u274c \u042d\u0442\u043e\u0442 \u0442\u0430\u0440\u0438\u0444 \u043d\u0435\u043b\u044c\u0437\u044f \u043e\u043f\u043b\u0430\u0442\u0438\u0442\u044c",
            show_alert=True,
        )
        return

    price_rub: int = PLAN_PRICES[plan]
    plan_name = PLAN_NAMES[plan]
    description = PLAN_DESCRIPTIONS.get(plan, "")

    # Telegram Payments use kopecks (1 ruble = 100 kopecks)
    prices = [
        LabeledPrice(
            label=f"PriceRadar {plan_name} (30 \u0434\u043d\u0435\u0439)",
            amount=price_rub * 100,
        ),
    ]

    provider_token = settings.YUKASSA_SECRET_KEY

    await callback.message.answer_invoice(
        title=f"PriceRadar {plan_name}",
        description=(
            f"\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 {plan_name} \u043d\u0430 30 \u0434\u043d\u0435\u0439.\n"
            f"\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c: {price_rub} \u20bd"
        ),
        payload=f"subscription:{plan.value}",
        provider_token=provider_token,
        currency="RUB",
        prices=prices,
        start_parameter=f"subscribe_{plan.value}",
        need_name=False,
        need_phone_number=False,
        need_email=True,
        send_phone_number_to_provider=False,
        send_email_to_provider=True,
    )

    await callback.answer()

    logger.info(
        "invoice_sent",
        telegram_id=callback.from_user.id,
        plan=plan.value,
        amount_rub=price_rub,
    )


# ---------------------------------------------------------------------------
# Pre-checkout query
# ---------------------------------------------------------------------------

@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout: PreCheckoutQuery) -> None:
    """Validate the payment before Telegram processes it.

    We always approve here; real validation (stock, plan availability)
    can be added as needed.
    """
    payload = pre_checkout.invoice_payload
    if not payload.startswith("subscription:"):
        await pre_checkout.answer(
            ok=False,
            error_message="\u274c \u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0442\u0438\u043f \u043f\u043b\u0430\u0442\u0435\u0436\u0430.",
        )
        return

    plan_key = payload.split(":")[1]
    try:
        SubscriptionPlan(plan_key)
    except ValueError:
        await pre_checkout.answer(
            ok=False,
            error_message="\u274c \u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0442\u0430\u0440\u0438\u0444.",
        )
        return

    await pre_checkout.answer(ok=True)
    logger.info(
        "pre_checkout_approved",
        telegram_id=pre_checkout.from_user.id,
        payload=payload,
        total_amount=pre_checkout.total_amount,
    )


# ---------------------------------------------------------------------------
# Successful payment
# ---------------------------------------------------------------------------

@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    """Handle a successful Telegram payment and activate the subscription."""
    if message.from_user is None or message.successful_payment is None:
        return

    payment = message.successful_payment
    payload = payment.invoice_payload

    if not payload.startswith("subscription:"):
        logger.warning("unknown_payment_payload", payload=payload)
        return

    plan_key = payload.split(":")[1]
    try:
        plan = SubscriptionPlan(plan_key)
    except ValueError:
        logger.error("invalid_plan_in_payment", plan_key=plan_key)
        return

    async with async_session_factory() as session:
        sub_svc = SubscriptionService(session)
        user: User = await sub_svc.get_or_create_user(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            username=message.from_user.username,
        )
        await sub_svc.activate_subscription(user, plan)
        await session.commit()

    plan_name = PLAN_NAMES[plan]

    logger.info(
        "payment_successful",
        telegram_id=message.from_user.id,
        plan=plan.value,
        total_amount=payment.total_amount,
        currency=payment.currency,
        provider_payment_charge_id=payment.provider_payment_charge_id,
    )

    await message.answer(
        f"\u2705 \u041e\u043f\u043b\u0430\u0442\u0430 \u043f\u0440\u043e\u0448\u043b\u0430 \u0443\u0441\u043f\u0435\u0448\u043d\u043e!\n\n"
        f"\U0001f451 \u0422\u0430\u0440\u0438\u0444 <b>{plan_name}</b> \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d \u043d\u0430 30 \u0434\u043d\u0435\u0439.\n\n"
        f"\u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443!",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
