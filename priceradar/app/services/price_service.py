from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Marketplace, PriceHistory, TrackedProduct
from app.models.user import PLAN_LIMITS, User
from app.parsers import PARSERS
from app.parsers.base import ParsedProduct

logger = structlog.get_logger()


class PriceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_products(
        self, user_id: int, active_only: bool = True
    ) -> list[TrackedProduct]:
        stmt = select(TrackedProduct).where(TrackedProduct.user_id == user_id)
        if active_only:
            stmt = stmt.where(TrackedProduct.is_active.is_(True))
        stmt = stmt.order_by(TrackedProduct.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_product_by_id(self, product_id: int) -> TrackedProduct | None:
        return await self.session.get(TrackedProduct, product_id)

    async def get_user_product_count(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(TrackedProduct)
            .where(
                and_(
                    TrackedProduct.user_id == user_id,
                    TrackedProduct.is_active.is_(True),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def can_add_product(self, user: User) -> bool:
        current_count = await self.get_user_product_count(user.id)
        limits = PLAN_LIMITS[user.subscription_plan]
        return current_count < limits["max_products"]

    async def add_product(
        self, user: User, url: str
    ) -> TrackedProduct:
        if not await self.can_add_product(user):
            limits = PLAN_LIMITS[user.subscription_plan]
            raise ValueError(
                f"Product limit reached ({limits['max_products']} "
                f"for {user.subscription_plan.value} plan)"
            )

        from app.parsers.base import BaseParser

        marketplace = BaseParser.detect_marketplace(url)
        if marketplace is None:
            raise ValueError("Unsupported marketplace URL")

        parser_cls = PARSERS.get(marketplace)
        if parser_cls is None:
            raise ValueError(f"No parser available for {marketplace}")

        parser = parser_cls()
        product_id = parser.extract_product_id(url)

        existing = await self.session.execute(
            select(TrackedProduct).where(
                and_(
                    TrackedProduct.user_id == user.id,
                    TrackedProduct.marketplace == Marketplace(marketplace),
                    TrackedProduct.external_id == product_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Product is already being tracked")

        parsed = await parser.parse_product(url)

        product = TrackedProduct(
            user_id=user.id,
            marketplace=Marketplace(marketplace),
            external_id=parsed.external_id,
            url=parser.build_url(parsed.external_id),
            title=parsed.title,
            current_price=parsed.price,
            image_url=parsed.image_url,
            price_updated_at=datetime.now(timezone.utc),
        )
        self.session.add(product)
        await self.session.flush()

        history = PriceHistory(
            product_id=product.id,
            price=parsed.price,
            original_price=parsed.original_price,
            discount_percent=parsed.discount_percent,
            in_stock=parsed.in_stock,
        )
        self.session.add(history)

        logger.info(
            "product_added",
            user_id=user.id,
            marketplace=marketplace,
            external_id=parsed.external_id,
            price=str(parsed.price),
        )
        return product

    async def remove_product(self, product_id: int, user_id: int) -> bool:
        product = await self.get_product_by_id(product_id)
        if product is None or product.user_id != user_id:
            return False
        product.is_active = False
        return True

    async def delete_product(self, product_id: int, user_id: int) -> bool:
        product = await self.get_product_by_id(product_id)
        if product is None or product.user_id != user_id:
            return False
        await self.session.delete(product)
        return True

    async def update_product_price(
        self, product: TrackedProduct, parsed: ParsedProduct
    ) -> bool:
        """Returns True if price actually changed."""
        price_changed = product.current_price != parsed.price

        if price_changed:
            product.previous_price = product.current_price
            product.current_price = parsed.price

        product.title = parsed.title
        product.image_url = parsed.image_url
        product.price_updated_at = datetime.now(timezone.utc)
        product.parse_errors_count = 0

        history = PriceHistory(
            product_id=product.id,
            price=parsed.price,
            original_price=parsed.original_price,
            discount_percent=parsed.discount_percent,
            in_stock=parsed.in_stock,
        )
        self.session.add(history)

        if price_changed:
            logger.info(
                "price_changed",
                product_id=product.id,
                old_price=str(product.previous_price),
                new_price=str(parsed.price),
            )

        return price_changed

    async def increment_parse_error(self, product: TrackedProduct) -> None:
        product.parse_errors_count += 1

    async def get_price_history(
        self, product_id: int, days: int = 30
    ) -> list[PriceHistory]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(PriceHistory)
            .where(
                and_(
                    PriceHistory.product_id == product_id,
                    PriceHistory.recorded_at >= since,
                )
            )
            .order_by(PriceHistory.recorded_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_min_price(
        self, product_id: int, days: int = 30
    ) -> Decimal | None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(func.min(PriceHistory.price))
            .where(
                and_(
                    PriceHistory.product_id == product_id,
                    PriceHistory.recorded_at >= since,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_price_trend(
        self, product_id: int, days: int = 7
    ) -> float | None:
        """Positive = price went up, negative = went down, None = not enough data."""
        history = await self.get_price_history(product_id, days)
        if len(history) < 2:
            return None

        first_price = history[0].price
        last_price = history[-1].price

        if first_price == 0:
            return None

        return float((last_price - first_price) / first_price * 100)

    async def cleanup_old_prices(self, days: int = 90) -> int:
        """Returns the number of deleted records."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(PriceHistory)
            .where(PriceHistory.recorded_at < cutoff)
        )
        result = await self.session.execute(stmt)
        records = result.scalars().all()
        count = len(records)
        for record in records:
            await self.session.delete(record)

        logger.info("old_prices_cleaned", deleted_count=count, older_than_days=days)
        return count
