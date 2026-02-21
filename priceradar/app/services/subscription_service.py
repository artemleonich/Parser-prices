from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import TrackedProduct
from app.models.user import PLAN_LIMITS, SubscriptionPlan, User

logger = structlog.get_logger()

PLAN_PRICES = {
    SubscriptionPlan.BASIC: 990,
    SubscriptionPlan.PRO: 2490,
}

PLAN_DURATION_DAYS = 30


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None = None,
    ) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is not None:
            user.first_name = first_name
            if username:
                user.telegram_username = username
            return user

        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            telegram_username=username,
            subscription_plan=SubscriptionPlan.FREE,
            max_tracked_products=PLAN_LIMITS[SubscriptionPlan.FREE]["max_products"],
        )
        self.session.add(user)
        await self.session.flush()

        logger.info("user_created", telegram_id=telegram_id, first_name=first_name)
        return user

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def activate_subscription(
        self, user: User, plan: SubscriptionPlan
    ) -> None:
        now = datetime.now(timezone.utc)

        # extend if current sub is still active on the same plan
        if (
            user.subscription_expires_at
            and user.subscription_expires_at > now
            and user.subscription_plan == plan
        ):
            user.subscription_expires_at += timedelta(days=PLAN_DURATION_DAYS)
        else:
            user.subscription_expires_at = now + timedelta(days=PLAN_DURATION_DAYS)

        user.subscription_plan = plan
        user.max_tracked_products = PLAN_LIMITS[plan]["max_products"]

        logger.info(
            "subscription_activated",
            user_id=user.id,
            plan=plan.value,
            expires_at=user.subscription_expires_at.isoformat(),
        )

    async def check_and_downgrade_expired(self, user: User) -> bool:
        """Returns True if user was downgraded."""
        if user.subscription_plan == SubscriptionPlan.FREE:
            return False

        if user.is_subscription_active:
            return False

        old_plan = user.subscription_plan
        user.subscription_plan = SubscriptionPlan.FREE
        user.max_tracked_products = PLAN_LIMITS[SubscriptionPlan.FREE]["max_products"]

        await self._deactivate_excess_products(user)

        logger.info(
            "subscription_downgraded",
            user_id=user.id,
            old_plan=old_plan.value,
        )
        return True

    async def _deactivate_excess_products(self, user: User) -> int:
        """Returns number of deactivated products."""
        limit = PLAN_LIMITS[user.subscription_plan]["max_products"]
        stmt = (
            select(TrackedProduct)
            .where(
                TrackedProduct.user_id == user.id,
                TrackedProduct.is_active.is_(True),
            )
            .order_by(TrackedProduct.created_at.asc())
        )
        result = await self.session.execute(stmt)
        products = list(result.scalars().all())

        deactivated = 0
        # keep the oldest products, deactivate the rest
        for product in products[limit:]:
            product.is_active = False
            deactivated += 1

        if deactivated:
            logger.info(
                "excess_products_deactivated",
                user_id=user.id,
                count=deactivated,
            )

        return deactivated

    def get_plan_info(self, plan: SubscriptionPlan) -> dict:
        limits = PLAN_LIMITS[plan]
        return {
            "name": plan.value,
            "price": PLAN_PRICES.get(plan, 0),
            "duration_days": PLAN_DURATION_DAYS,
            **limits,
        }

    def format_subscription_info(self, user: User) -> str:
        plan_names = {
            SubscriptionPlan.FREE: "Free",
            SubscriptionPlan.BASIC: "Basic (990 \u20bd/\u043c\u0435\u0441)",
            SubscriptionPlan.PRO: "Pro (2 490 \u20bd/\u043c\u0435\u0441)",
        }
        limits = PLAN_LIMITS[user.subscription_plan]

        lines = [
            f"\U0001f4cb \u0412\u0430\u0448 \u0442\u0430\u0440\u0438\u0444: {plan_names[user.subscription_plan]}",
            "",
            f"\U0001f4e6 \u041c\u0430\u043a\u0441. \u0442\u043e\u0432\u0430\u0440\u043e\u0432: {limits['max_products']}",
            f"\U0001f514 \u041c\u0430\u043a\u0441. \u0430\u043b\u0435\u0440\u0442\u043e\u0432: {limits['max_alerts']}",
            f"\U0001f3ea \u041c\u0430\u0440\u043a\u0435\u0442\u043f\u043b\u0435\u0439\u0441\u043e\u0432: {limits['max_marketplaces']}",
            f"\U0001f4c5 \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0446\u0435\u043d: {limits['history_days']} \u0434\u043d\u0435\u0439",
            f"\U0001f4be \u042d\u043a\u0441\u043f\u043e\u0440\u0442 CSV: {'\u2705' if limits['csv_export'] else '\u274c'}",
        ]

        if user.subscription_plan != SubscriptionPlan.FREE:
            if user.subscription_expires_at:
                exp = user.subscription_expires_at.strftime("%d.%m.%Y")
                lines.append(f"\n\u23f0 \u0414\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442 \u0434\u043e: {exp}")

        return "\n".join(lines)
