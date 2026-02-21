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

PLAN_NAMES: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.FREE: "Free",
    SubscriptionPlan.BASIC: "Basic",
    SubscriptionPlan.PRO: "Pro",
}

PLAN_DESCRIPTIONS: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.BASIC: (
        "\u2b50 <b>Basic</b> \u2014 990 \u20bd/мес\n"
        "\u2022 До 50 товаров\n"
        "\u2022 20 алертов\n"
        "\u2022 3 маркетплейса\n"
        "\u2022 История 30 дней\n"
        "\u2022 Экспорт CSV"
    ),
    SubscriptionPlan.PRO: (
        "\U0001f451 <b>Pro</b> \u2014 2 490 \u20bd/мес\n"
        "\u2022 До 200 товаров\n"
        "\u2022 Безлимит алертов\n"
        "\u2022 3 маркетплейса\n"
        "\u2022 История 90 дней\n"
        "\u2022 Экспорт CSV"
    ),
}


@router.callback_query(F.data == "subscription")
async def cb_subscription(callback: CallbackQuery) -> None:
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
        "\u2b06\ufe0f Выберите тариф для оплаты:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=subscription_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subscribe:"))
async def cb_subscribe(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    plan_key = callback.data.split(":")[1]
    try:
        plan = SubscriptionPlan(plan_key)
    except ValueError:
        await callback.answer(
            "\u274c Неизвестный тариф",
            show_alert=True,
        )
        return

    if plan not in PLAN_PRICES:
        await callback.answer(
            "\u274c Этот тариф нельзя оплатить",
            show_alert=True,
        )
        return

    price_rub: int = PLAN_PRICES[plan]
    plan_name = PLAN_NAMES[plan]
    description = PLAN_DESCRIPTIONS.get(plan, "")

    # в копейках для Telegram Payments
    prices = [
        LabeledPrice(
            label=f"PriceRadar {plan_name} (30 дней)",
            amount=price_rub * 100,
        ),
    ]

    provider_token = settings.YUKASSA_SECRET_KEY

    await callback.message.answer_invoice(
        title=f"PriceRadar {plan_name}",
        description=(
            f"Подписка {plan_name} на 30 дней.\n"
            f"Стоимость: {price_rub} \u20bd"
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


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout: PreCheckoutQuery) -> None:
    payload = pre_checkout.invoice_payload
    if not payload.startswith("subscription:"):
        await pre_checkout.answer(
            ok=False,
            error_message="\u274c Неизвестный тип платежа.",
        )
        return

    plan_key = payload.split(":")[1]
    try:
        SubscriptionPlan(plan_key)
    except ValueError:
        await pre_checkout.answer(
            ok=False,
            error_message="\u274c Неизвестный тариф.",
        )
        return

    await pre_checkout.answer(ok=True)
    logger.info(
        "pre_checkout_approved",
        telegram_id=pre_checkout.from_user.id,
        payload=payload,
        total_amount=pre_checkout.total_amount,
    )


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
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
        f"\u2705 Оплата прошла успешно!\n\n"
        f"\U0001f451 Тариф <b>{plan_name}</b> активирован на 30 дней.\n\n"
        f"Спасибо за поддержку!",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
