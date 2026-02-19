"""Unit tests for PriceService."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Marketplace, PriceHistory, TrackedProduct
from app.models.user import SubscriptionPlan, User
from app.parsers.base import ParsedProduct
from app.services.price_service import PriceService


# ---------------------------------------------------------------------------
# add_product
# ---------------------------------------------------------------------------


class TestAddProduct:
    """Tests for PriceService.add_product."""

    @pytest.mark.asyncio
    async def test_add_product_success(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Adding a valid Wildberries URL creates a TrackedProduct."""
        parsed = ParsedProduct(
            external_id="55555555",
            title="New WB Product",
            price=Decimal("3990.00"),
            original_price=Decimal("5990.00"),
            discount_percent=33,
            in_stock=True,
            image_url="https://basket-01.wbbasket.ru/img.webp",
        )

        mock_parser_instance = MagicMock()
        mock_parser_instance.extract_product_id.return_value = "55555555"
        mock_parser_instance.parse_product = AsyncMock(return_value=parsed)
        mock_parser_instance.build_url.return_value = (
            "https://www.wildberries.ru/catalog/55555555/detail.aspx"
        )

        mock_parser_cls = MagicMock(return_value=mock_parser_instance)

        with patch("app.services.price_service.PARSERS", {"wildberries": mock_parser_cls}):
            service = PriceService(db_session)
            product = await service.add_product(
                test_user,
                "https://www.wildberries.ru/catalog/55555555/detail.aspx",
            )

        assert product.external_id == "55555555"
        assert product.title == "New WB Product"
        assert product.current_price == Decimal("3990.00")
        assert product.marketplace == Marketplace.WILDBERRIES
        assert product.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_add_product_limit_reached(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Adding a product when the user is at their limit raises ValueError."""
        # Fill up to the FREE limit (5 products).
        for i in range(5):
            p = TrackedProduct(
                user_id=test_user.id,
                marketplace=Marketplace.WILDBERRIES,
                external_id=f"limit_{i}",
                url=f"https://www.wildberries.ru/catalog/limit_{i}/detail.aspx",
                title=f"Limit Product {i}",
                is_active=True,
            )
            db_session.add(p)
        await db_session.flush()

        service = PriceService(db_session)

        with pytest.raises(ValueError, match="Product limit reached"):
            await service.add_product(
                test_user,
                "https://www.wildberries.ru/catalog/99999999/detail.aspx",
            )

    @pytest.mark.asyncio
    async def test_add_product_unsupported_marketplace(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """An unsupported marketplace URL raises ValueError."""
        service = PriceService(db_session)

        with pytest.raises(ValueError, match="Unsupported marketplace URL"):
            await service.add_product(test_user, "https://amazon.com/dp/B012345678")

    @pytest.mark.asyncio
    async def test_add_product_duplicate(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        """Adding a product that already exists raises ValueError."""
        parsed = ParsedProduct(
            external_id=test_product.external_id,
            title="Duplicate",
            price=Decimal("1000"),
        )

        mock_parser_instance = MagicMock()
        mock_parser_instance.extract_product_id.return_value = test_product.external_id
        mock_parser_instance.parse_product = AsyncMock(return_value=parsed)
        mock_parser_instance.build_url.return_value = test_product.url

        mock_parser_cls = MagicMock(return_value=mock_parser_instance)

        with patch("app.services.price_service.PARSERS", {"wildberries": mock_parser_cls}):
            service = PriceService(db_session)

            with pytest.raises(ValueError, match="already being tracked"):
                await service.add_product(
                    test_user,
                    f"https://www.wildberries.ru/catalog/{test_product.external_id}/detail.aspx",
                )


# ---------------------------------------------------------------------------
# get_user_products
# ---------------------------------------------------------------------------


class TestGetUserProducts:
    """Tests for PriceService.get_user_products."""

    @pytest.mark.asyncio
    async def test_get_user_products_returns_active(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        """Active products are returned by default."""
        service = PriceService(db_session)
        products = await service.get_user_products(test_user.id)
        assert len(products) == 1
        assert products[0].id == test_product.id

    @pytest.mark.asyncio
    async def test_get_user_products_excludes_inactive(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Inactive products are excluded when active_only=True."""
        inactive = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.WILDBERRIES,
            external_id="inactive_001",
            url="https://www.wildberries.ru/catalog/inactive_001/detail.aspx",
            title="Inactive Product",
            is_active=False,
        )
        db_session.add(inactive)
        await db_session.flush()

        service = PriceService(db_session)
        products = await service.get_user_products(test_user.id, active_only=True)
        assert all(p.is_active for p in products)

    @pytest.mark.asyncio
    async def test_get_user_products_includes_inactive(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """All products returned when active_only=False."""
        inactive = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.WILDBERRIES,
            external_id="inactive_002",
            url="https://www.wildberries.ru/catalog/inactive_002/detail.aspx",
            title="Inactive Product 2",
            is_active=False,
        )
        db_session.add(inactive)
        await db_session.flush()

        service = PriceService(db_session)
        products = await service.get_user_products(test_user.id, active_only=False)
        assert any(not p.is_active for p in products)

    @pytest.mark.asyncio
    async def test_get_user_products_empty_for_unknown_user(
        self, db_session: AsyncSession,
    ) -> None:
        """Unknown user_id returns an empty list."""
        service = PriceService(db_session)
        products = await service.get_user_products(999999)
        assert products == []


# ---------------------------------------------------------------------------
# update_product_price
# ---------------------------------------------------------------------------


class TestUpdateProductPrice:
    """Tests for PriceService.update_product_price."""

    @pytest.mark.asyncio
    async def test_update_product_price_changed(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """When price differs, the method updates and returns True."""
        parsed = ParsedProduct(
            external_id=test_product.external_id,
            title="Updated Title",
            price=Decimal("7990.00"),
            original_price=Decimal("12990.00"),
            discount_percent=38,
            in_stock=True,
            image_url="https://basket-01.wbbasket.ru/new_img.webp",
        )

        service = PriceService(db_session)
        changed = await service.update_product_price(test_product, parsed)

        assert changed is True
        assert test_product.current_price == Decimal("7990.00")
        assert test_product.previous_price == Decimal("8490.00")
        assert test_product.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_product_price_unchanged(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """When the price is the same, the method returns False."""
        parsed = ParsedProduct(
            external_id=test_product.external_id,
            title=test_product.title,
            price=test_product.current_price,
            in_stock=True,
        )

        service = PriceService(db_session)
        changed = await service.update_product_price(test_product, parsed)

        assert changed is False

    @pytest.mark.asyncio
    async def test_update_product_price_records_history(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """A PriceHistory record is created on every update."""
        parsed = ParsedProduct(
            external_id=test_product.external_id,
            title=test_product.title,
            price=Decimal("6000.00"),
            original_price=Decimal("10000.00"),
            discount_percent=40,
            in_stock=True,
        )

        service = PriceService(db_session)
        await service.update_product_price(test_product, parsed)
        await db_session.flush()

        history = await service.get_price_history(test_product.id, days=1)
        assert len(history) >= 1
        latest = history[-1]
        assert latest.price == Decimal("6000.00")
        assert latest.original_price == Decimal("10000.00")
        assert latest.discount_percent == 40

    @pytest.mark.asyncio
    async def test_update_resets_parse_errors(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """parse_errors_count is reset to 0 after successful update."""
        test_product.parse_errors_count = 3

        parsed = ParsedProduct(
            external_id=test_product.external_id,
            title=test_product.title,
            price=test_product.current_price,
            in_stock=True,
        )

        service = PriceService(db_session)
        await service.update_product_price(test_product, parsed)

        assert test_product.parse_errors_count == 0


# ---------------------------------------------------------------------------
# get_price_trend
# ---------------------------------------------------------------------------


class TestGetPriceTrend:
    """Tests for PriceService.get_price_trend."""

    @pytest.mark.asyncio
    async def test_price_trend_increasing(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """Positive trend when the latest price is higher than the earliest."""
        now = datetime.now(timezone.utc)

        h1 = PriceHistory(
            product_id=test_product.id,
            price=Decimal("1000.00"),
            in_stock=True,
            recorded_at=now - timedelta(days=3),
        )
        h2 = PriceHistory(
            product_id=test_product.id,
            price=Decimal("1200.00"),
            in_stock=True,
            recorded_at=now - timedelta(days=1),
        )
        db_session.add_all([h1, h2])
        await db_session.flush()

        service = PriceService(db_session)
        trend = await service.get_price_trend(test_product.id, days=7)

        assert trend is not None
        assert trend == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_price_trend_decreasing(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """Negative trend when the latest price is lower than the earliest."""
        now = datetime.now(timezone.utc)

        h1 = PriceHistory(
            product_id=test_product.id,
            price=Decimal("2000.00"),
            in_stock=True,
            recorded_at=now - timedelta(days=5),
        )
        h2 = PriceHistory(
            product_id=test_product.id,
            price=Decimal("1600.00"),
            in_stock=True,
            recorded_at=now - timedelta(days=1),
        )
        db_session.add_all([h1, h2])
        await db_session.flush()

        service = PriceService(db_session)
        trend = await service.get_price_trend(test_product.id, days=7)

        assert trend is not None
        assert trend == pytest.approx(-20.0)

    @pytest.mark.asyncio
    async def test_price_trend_insufficient_data(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """Returns None when there are fewer than 2 history records."""
        service = PriceService(db_session)
        trend = await service.get_price_trend(test_product.id, days=7)
        assert trend is None

    @pytest.mark.asyncio
    async def test_price_trend_flat(
        self, db_session: AsyncSession, test_product: TrackedProduct,
    ) -> None:
        """Returns 0.0 when price is unchanged."""
        now = datetime.now(timezone.utc)

        h1 = PriceHistory(
            product_id=test_product.id,
            price=Decimal("5000.00"),
            in_stock=True,
            recorded_at=now - timedelta(days=3),
        )
        h2 = PriceHistory(
            product_id=test_product.id,
            price=Decimal("5000.00"),
            in_stock=True,
            recorded_at=now - timedelta(days=1),
        )
        db_session.add_all([h1, h2])
        await db_session.flush()

        service = PriceService(db_session)
        trend = await service.get_price_trend(test_product.id, days=7)

        assert trend == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# can_add_product
# ---------------------------------------------------------------------------


class TestCanAddProduct:
    """Tests for PriceService.can_add_product limit checking."""

    @pytest.mark.asyncio
    async def test_can_add_product_free_plan_under_limit(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """FREE plan user with no products can add one."""
        service = PriceService(db_session)
        assert await service.can_add_product(test_user) is True

    @pytest.mark.asyncio
    async def test_cannot_add_product_free_plan_at_limit(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """FREE plan user with 5 products cannot add more."""
        for i in range(5):
            p = TrackedProduct(
                user_id=test_user.id,
                marketplace=Marketplace.WILDBERRIES,
                external_id=f"cancheck_{i}",
                url=f"https://www.wildberries.ru/catalog/cancheck_{i}/detail.aspx",
                title=f"Limit Product {i}",
                is_active=True,
            )
            db_session.add(p)
        await db_session.flush()

        service = PriceService(db_session)
        assert await service.can_add_product(test_user) is False

    @pytest.mark.asyncio
    async def test_can_add_product_basic_plan_higher_limit(
        self, db_session: AsyncSession,
    ) -> None:
        """BASIC plan has a higher limit (50) so adding is allowed."""
        basic_user = User(
            telegram_id=999999,
            first_name="Basic",
            subscription_plan=SubscriptionPlan.BASIC,
        )
        db_session.add(basic_user)
        await db_session.flush()

        service = PriceService(db_session)
        assert await service.can_add_product(basic_user) is True

    @pytest.mark.asyncio
    async def test_inactive_products_not_counted(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Inactive (deactivated) products do not count towards the limit."""
        for i in range(5):
            p = TrackedProduct(
                user_id=test_user.id,
                marketplace=Marketplace.WILDBERRIES,
                external_id=f"inactive_count_{i}",
                url=f"https://www.wildberries.ru/catalog/inactive_count_{i}/detail.aspx",
                title=f"Inactive Count {i}",
                is_active=False,
            )
            db_session.add(p)
        await db_session.flush()

        service = PriceService(db_session)
        assert await service.can_add_product(test_user) is True
