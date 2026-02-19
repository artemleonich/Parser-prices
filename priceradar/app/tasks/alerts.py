"""Celery tasks for alert checking and notification sending."""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session_factory
from app.models.product import TrackedProduct
from app.services.alert_service import AlertService
from app.services.price_service import PriceService
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


async def _send_telegram_alert(telegram_id: int, message: str, product_url: str) -> bool:
    """Send an alert message to a user via Telegram bot API."""
    import httpx

    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.warning("telegram_bot_token_not_set")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Build inline keyboard with link to product
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "\U0001f517 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 \u043c\u0430\u0440\u043a\u0435\u0442\u043f\u043b\u0435\u0439\u0441\u0435", "url": product_url},
            ]
        ]
    }

    payload = {
        "chat_id": telegram_id,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error("telegram_send_failed", telegram_id=telegram_id, error=str(e))
        return False


async def _check_all_alerts() -> dict:
    """Check recently updated products for triggered alerts and send notifications."""
    async with async_session_factory() as session:
        # Find products updated in the last 5 minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

        stmt = (
            select(TrackedProduct)
            .where(
                and_(
                    TrackedProduct.is_active.is_(True),
                    TrackedProduct.price_updated_at >= cutoff,
                    TrackedProduct.previous_price.isnot(None),
                    TrackedProduct.current_price != TrackedProduct.previous_price,
                )
            )
            .options(selectinload(TrackedProduct.user))
        )
        result = await session.execute(stmt)
        products = list(result.scalars().all())

        if not products:
            return {"checked": 0, "triggered": 0, "sent": 0}

        alert_svc = AlertService(session)
        price_svc = PriceService(session)

        triggered_count = 0
        sent_count = 0

        for product in products:
            logs = await alert_svc.process_product_alerts(product)
            triggered_count += len(logs)

            for log in logs:
                min_price = await price_svc.get_min_price(product.id, days=30)
                message = alert_svc.format_alert_message(log, product, min_price)

                sent = await _send_telegram_alert(
                    product.user.telegram_id,
                    message,
                    product.url,
                )
                if sent:
                    await alert_svc.mark_alert_sent(log)
                    sent_count += 1

        await session.commit()

        logger.info(
            "alerts_checked",
            products_checked=len(products),
            triggered=triggered_count,
            sent=sent_count,
        )

        return {
            "checked": len(products),
            "triggered": triggered_count,
            "sent": sent_count,
        }


@celery_app.task(name="app.tasks.alerts.check_all_alerts")
def check_all_alerts() -> dict:
    """Celery task: check all alerts for recently updated products."""
    return asyncio.run(_check_all_alerts())


async def _send_unsent_alerts() -> dict:
    """Retry sending any alerts that failed to send."""
    async with async_session_factory() as session:
        alert_svc = AlertService(session)
        price_svc = PriceService(session)

        unsent = await alert_svc.get_unsent_alerts()
        sent_count = 0

        for log in unsent:
            product = log.product
            if product is None:
                continue

            user = await session.get(
                __import__("app.models.user", fromlist=["User"]).User,
                product.user_id,
            )
            if user is None:
                continue

            min_price = await price_svc.get_min_price(product.id, days=30)
            message = alert_svc.format_alert_message(log, product, min_price)

            sent = await _send_telegram_alert(
                user.telegram_id,
                message,
                product.url,
            )
            if sent:
                await alert_svc.mark_alert_sent(log)
                sent_count += 1

        await session.commit()
        return {"retried": len(unsent), "sent": sent_count}


@celery_app.task(name="app.tasks.alerts.send_unsent_alerts")
def send_unsent_alerts() -> dict:
    """Celery task: retry sending failed alert notifications."""
    return asyncio.run(_send_unsent_alerts())
