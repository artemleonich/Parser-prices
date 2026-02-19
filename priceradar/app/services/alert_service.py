"""Business logic for alert rules and notifications."""

from datetime import datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import AlertLog, AlertRule, RuleType
from app.models.product import TrackedProduct

logger = structlog.get_logger()


class AlertService:
    """Service for managing alert rules and checking triggers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_alert_rule(
        self,
        user_id: int,
        rule_type: RuleType,
        product_id: int | None = None,
        threshold_value: Decimal | None = None,
    ) -> AlertRule:
        """Create a new alert rule."""
        rule = AlertRule(
            user_id=user_id,
            product_id=product_id,
            rule_type=rule_type,
            threshold_value=threshold_value,
        )
        self.session.add(rule)
        await self.session.flush()

        logger.info(
            "alert_rule_created",
            rule_id=rule.id,
            user_id=user_id,
            rule_type=rule_type.value,
        )
        return rule

    async def get_user_alert_rules(
        self, user_id: int, active_only: bool = True
    ) -> list[AlertRule]:
        """Get all alert rules for a user."""
        stmt = select(AlertRule).where(AlertRule.user_id == user_id)
        if active_only:
            stmt = stmt.where(AlertRule.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_product_alert_rules(
        self, user_id: int, product_id: int
    ) -> list[AlertRule]:
        """Get alert rules for a specific product (including global rules)."""
        stmt = (
            select(AlertRule)
            .where(
                and_(
                    AlertRule.user_id == user_id,
                    AlertRule.is_active.is_(True),
                    (
                        (AlertRule.product_id == product_id)
                        | (AlertRule.product_id.is_(None))
                    ),
                )
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_alert_rule(self, rule_id: int, user_id: int) -> bool:
        """Delete an alert rule."""
        rule = await self.session.get(AlertRule, rule_id)
        if rule is None or rule.user_id != user_id:
            return False
        await self.session.delete(rule)
        return True

    async def check_alert(
        self,
        rule: AlertRule,
        product: TrackedProduct,
    ) -> bool:
        """Check if an alert rule is triggered for a product.

        Returns True if the alert should fire.
        """
        if product.current_price is None or product.previous_price is None:
            # Special case: back_in_stock doesn't need price comparison
            if rule.rule_type == RuleType.BACK_IN_STOCK:
                return False  # Handled separately via in_stock flag
            return False

        old_price = product.previous_price
        new_price = product.current_price

        if old_price == new_price:
            return False

        match rule.rule_type:
            case RuleType.PRICE_DROP:
                if old_price <= 0:
                    return False
                drop_pct = (old_price - new_price) / old_price * 100
                threshold = rule.threshold_value or Decimal("0")
                return drop_pct >= threshold

            case RuleType.PRICE_RISE:
                if old_price <= 0:
                    return False
                rise_pct = (new_price - old_price) / old_price * 100
                threshold = rule.threshold_value or Decimal("0")
                return rise_pct >= threshold

            case RuleType.PRICE_BELOW:
                if rule.threshold_value is None:
                    return False
                return new_price <= rule.threshold_value

            case RuleType.PRICE_ABOVE:
                if rule.threshold_value is None:
                    return False
                return new_price >= rule.threshold_value

            case RuleType.BACK_IN_STOCK:
                return False  # Handled via stock status, not price

        return False

    async def process_product_alerts(
        self, product: TrackedProduct
    ) -> list[AlertLog]:
        """Check all alert rules for a product and create logs for triggered ones."""
        rules = await self.get_product_alert_rules(product.user_id, product.id)
        triggered_logs: list[AlertLog] = []

        for rule in rules:
            if await self.check_alert(rule, product):
                log = AlertLog(
                    alert_rule_id=rule.id,
                    product_id=product.id,
                    old_price=product.previous_price or Decimal("0"),
                    new_price=product.current_price or Decimal("0"),
                    message_sent=False,
                )
                self.session.add(log)
                triggered_logs.append(log)

                logger.info(
                    "alert_triggered",
                    rule_id=rule.id,
                    product_id=product.id,
                    rule_type=rule.rule_type.value,
                    old_price=str(product.previous_price),
                    new_price=str(product.current_price),
                )

        if triggered_logs:
            await self.session.flush()

        return triggered_logs

    async def mark_alert_sent(self, alert_log: AlertLog) -> None:
        """Mark an alert log as successfully sent."""
        alert_log.message_sent = True
        alert_log.sent_at = datetime.now(timezone.utc)

    async def get_unsent_alerts(self) -> list[AlertLog]:
        """Get all unsent alert logs with related data."""
        stmt = (
            select(AlertLog)
            .where(AlertLog.message_sent.is_(False))
            .options(
                selectinload(AlertLog.alert_rule),
                selectinload(AlertLog.product),
            )
            .order_by(AlertLog.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def format_alert_message(
        self,
        log: AlertLog,
        product: TrackedProduct,
        min_price_30d: Decimal | None = None,
    ) -> str:
        """Format an alert message for Telegram."""
        old_price = log.old_price
        new_price = log.new_price

        if old_price > 0:
            change_pct = (new_price - old_price) / old_price * 100
            change_sign = "+" if change_pct > 0 else ""
            change_str = f"{change_sign}{change_pct:.1f}%"
        else:
            change_str = "N/A"

        emoji = "\U0001f514"  # bell
        if new_price < old_price:
            header = f"{emoji} \u0421\u043d\u0438\u0436\u0435\u043d\u0438\u0435 \u0446\u0435\u043d\u044b!"
        else:
            header = f"{emoji} \u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435 \u0446\u0435\u043d\u044b!"

        marketplace_labels = {
            "wildberries": "Wildberries",
            "ozon": "Ozon",
            "yandex_market": "\u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0430\u0440\u043a\u0435\u0442",
        }
        mp_label = marketplace_labels.get(product.marketplace.value, product.marketplace.value)

        lines = [
            header,
            "",
            f"\U0001f4e6 {product.title}",
            f"\U0001f3ea {mp_label}",
            f"\U0001f4b0 \u041d\u043e\u0432\u0430\u044f \u0446\u0435\u043d\u0430: {new_price:,.0f} \u20bd",
            f"\U0001f4c9 \u0411\u044b\u043b\u043e: {old_price:,.0f} \u20bd ({change_str})",
        ]

        if min_price_30d is not None:
            lines.append(
                f"\U0001f4ca \u041c\u0438\u043d. \u0437\u0430 30 \u0434\u043d\u0435\u0439: {min_price_30d:,.0f} \u20bd"
            )

        return "\n".join(lines)
