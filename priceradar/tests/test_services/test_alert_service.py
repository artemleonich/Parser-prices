from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertLog, AlertRule, RuleType
from app.models.product import Marketplace, TrackedProduct
from app.models.user import User
from app.services.alert_service import AlertService


class TestCreateAlertRule:

    @pytest.mark.asyncio
    async def test_create_price_drop_rule(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=test_product.id,
            threshold_value=Decimal("10"),
        )

        assert rule.id is not None
        assert rule.user_id == test_user.id
        assert rule.product_id == test_product.id
        assert rule.rule_type == RuleType.PRICE_DROP
        assert rule.threshold_value == Decimal("10")
        assert rule.is_active is True

    @pytest.mark.asyncio
    async def test_create_global_rule_without_product(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_BELOW,
            threshold_value=Decimal("5000"),
        )

        assert rule.product_id is None
        assert rule.rule_type == RuleType.PRICE_BELOW
        assert rule.threshold_value == Decimal("5000")

    @pytest.mark.asyncio
    async def test_create_rule_all_types(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        service = AlertService(db_session)
        for rule_type in RuleType:
            rule = await service.create_alert_rule(
                user_id=test_user.id,
                rule_type=rule_type,
            )
            assert rule.rule_type == rule_type


class TestCheckAlertPriceDrop:

    @pytest.mark.asyncio
    async def test_price_drop_triggered(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=test_product.id,
            threshold_value=Decimal("10"),
        )

        result = await service.check_alert(rule, test_product)
        assert result is True

    @pytest.mark.asyncio
    async def test_price_drop_not_triggered_below_threshold(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=test_product.id,
            threshold_value=Decimal("50"),
        )

        result = await service.check_alert(rule, test_product)
        assert result is False

    @pytest.mark.asyncio
    async def test_price_drop_no_previous_price(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        product = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.WILDBERRIES,
            external_id="no_prev_001",
            url="https://www.wildberries.ru/catalog/no_prev_001/detail.aspx",
            title="No Previous Price",
            current_price=Decimal("5000"),
            previous_price=None,
            is_active=True,
        )
        db_session.add(product)
        await db_session.flush()

        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=product.id,
            threshold_value=Decimal("5"),
        )

        result = await service.check_alert(rule, product)
        assert result is False


class TestCheckAlertPriceRise:

    @pytest.mark.asyncio
    async def test_price_rise_triggered(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        product = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.OZON,
            external_id="rise_001",
            url="https://www.ozon.ru/product/rise_001/",
            title="Rising Product",
            current_price=Decimal("12000"),
            previous_price=Decimal("10000"),
            is_active=True,
        )
        db_session.add(product)
        await db_session.flush()

        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_RISE,
            product_id=product.id,
            threshold_value=Decimal("15"),
        )

        result = await service.check_alert(rule, product)
        assert result is True

    @pytest.mark.asyncio
    async def test_price_rise_not_triggered(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        product = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.OZON,
            external_id="rise_002",
            url="https://www.ozon.ru/product/rise_002/",
            title="Slight Rise Product",
            current_price=Decimal("10500"),
            previous_price=Decimal("10000"),
            is_active=True,
        )
        db_session.add(product)
        await db_session.flush()

        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_RISE,
            product_id=product.id,
            threshold_value=Decimal("10"),
        )

        result = await service.check_alert(rule, product)
        assert result is False


class TestCheckAlertPriceBelow:

    @pytest.mark.asyncio
    async def test_price_below_triggered(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_BELOW,
            product_id=test_product.id,
            threshold_value=Decimal("9000"),
        )

        result = await service.check_alert(rule, test_product)
        assert result is True

    @pytest.mark.asyncio
    async def test_price_below_not_triggered(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_BELOW,
            product_id=test_product.id,
            threshold_value=Decimal("5000"),
        )

        result = await service.check_alert(rule, test_product)
        assert result is False

    @pytest.mark.asyncio
    async def test_price_below_no_threshold_returns_false(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_BELOW,
            product_id=test_product.id,
            threshold_value=None,
        )

        result = await service.check_alert(rule, test_product)
        assert result is False


class TestCheckAlertPriceAbove:

    @pytest.mark.asyncio
    async def test_price_above_triggered(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        product = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.WILDBERRIES,
            external_id="above_001",
            url="https://www.wildberries.ru/catalog/above_001/detail.aspx",
            title="Above Product",
            current_price=Decimal("15000"),
            previous_price=Decimal("12000"),
            is_active=True,
        )
        db_session.add(product)
        await db_session.flush()

        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_ABOVE,
            product_id=product.id,
            threshold_value=Decimal("14000"),
        )

        result = await service.check_alert(rule, product)
        assert result is True

    @pytest.mark.asyncio
    async def test_price_above_not_triggered(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        product = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.WILDBERRIES,
            external_id="above_002",
            url="https://www.wildberries.ru/catalog/above_002/detail.aspx",
            title="Below Threshold Product",
            current_price=Decimal("10000"),
            previous_price=Decimal("9000"),
            is_active=True,
        )
        db_session.add(product)
        await db_session.flush()

        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_ABOVE,
            product_id=product.id,
            threshold_value=Decimal("12000"),
        )

        result = await service.check_alert(rule, product)
        assert result is False

    @pytest.mark.asyncio
    async def test_price_above_no_threshold_returns_false(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)
        rule = await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_ABOVE,
            product_id=test_product.id,
            threshold_value=None,
        )

        result = await service.check_alert(rule, test_product)
        assert result is False


class TestCheckAlertEqualPrices:

    @pytest.mark.asyncio
    async def test_no_alert_when_prices_equal(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        product = TrackedProduct(
            user_id=test_user.id,
            marketplace=Marketplace.WILDBERRIES,
            external_id="equal_001",
            url="https://www.wildberries.ru/catalog/equal_001/detail.aspx",
            title="Equal Price Product",
            current_price=Decimal("5000"),
            previous_price=Decimal("5000"),
            is_active=True,
        )
        db_session.add(product)
        await db_session.flush()

        service = AlertService(db_session)

        for rule_type in (RuleType.PRICE_DROP, RuleType.PRICE_RISE):
            rule = await service.create_alert_rule(
                user_id=test_user.id,
                rule_type=rule_type,
                product_id=product.id,
                threshold_value=Decimal("0"),
            )
            result = await service.check_alert(rule, product)
            assert result is False, f"{rule_type} should not fire on equal prices"


class TestProcessProductAlerts:

    @pytest.mark.asyncio
    async def test_process_product_alerts_triggered(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=test_product.id,
            threshold_value=Decimal("10"),
        )

        logs = await service.process_product_alerts(test_product)

        assert len(logs) == 1
        log = logs[0]
        assert log.product_id == test_product.id
        assert log.old_price == test_product.previous_price
        assert log.new_price == test_product.current_price
        assert log.message_sent is False

    @pytest.mark.asyncio
    async def test_process_product_alerts_none_triggered(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=test_product.id,
            threshold_value=Decimal("99"),
        )

        logs = await service.process_product_alerts(test_product)
        assert logs == []

    @pytest.mark.asyncio
    async def test_process_product_alerts_multiple_rules(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            product_id=test_product.id,
            threshold_value=Decimal("5"),
        )

        await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_BELOW,
            product_id=test_product.id,
            threshold_value=Decimal("9000"),
        )

        logs = await service.process_product_alerts(test_product)
        assert len(logs) == 2

    @pytest.mark.asyncio
    async def test_process_includes_global_rules(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        await service.create_alert_rule(
            user_id=test_user.id,
            rule_type=RuleType.PRICE_DROP,
            threshold_value=Decimal("10"),
        )

        logs = await service.process_product_alerts(test_product)
        assert len(logs) == 1


class TestFormatAlertMessage:

    @pytest.mark.asyncio
    async def test_format_price_decrease_message(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        log = AlertLog(
            alert_rule_id=1,
            product_id=test_product.id,
            old_price=Decimal("12990"),
            new_price=Decimal("8490"),
            message_sent=False,
        )

        message = service.format_alert_message(log, test_product)

        assert "Test Product" in message
        assert "Wildberries" in message
        assert "8,490" in message or "8490" in message
        assert "12,990" in message or "12990" in message
        assert "\u0421\u043d\u0438\u0436\u0435\u043d\u0438\u0435" in message

    @pytest.mark.asyncio
    async def test_format_price_increase_message(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        log = AlertLog(
            alert_rule_id=1,
            product_id=test_product.id,
            old_price=Decimal("5000"),
            new_price=Decimal("7000"),
            message_sent=False,
        )

        message = service.format_alert_message(log, test_product)

        assert "\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435" in message
        assert "+" in message

    @pytest.mark.asyncio
    async def test_format_message_with_min_price(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        log = AlertLog(
            alert_rule_id=1,
            product_id=test_product.id,
            old_price=Decimal("12990"),
            new_price=Decimal("8490"),
            message_sent=False,
        )

        message = service.format_alert_message(
            log, test_product, min_price_30d=Decimal("7990"),
        )

        assert "7,990" in message or "7990" in message
        assert "30" in message

    @pytest.mark.asyncio
    async def test_format_message_without_min_price(
        self, db_session: AsyncSession, test_user: User, test_product: TrackedProduct,
    ) -> None:
        service = AlertService(db_session)

        log = AlertLog(
            alert_rule_id=1,
            product_id=test_product.id,
            old_price=Decimal("10000"),
            new_price=Decimal("8000"),
            message_sent=False,
        )

        message = service.format_alert_message(log, test_product, min_price_30d=None)

        assert "\u041c\u0438\u043d. \u0437\u0430 30" not in message

    @pytest.mark.asyncio
    async def test_format_message_marketplace_labels(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        service = AlertService(db_session)

        for marketplace, expected_label in [
            (Marketplace.WILDBERRIES, "Wildberries"),
            (Marketplace.OZON, "Ozon"),
            (Marketplace.YANDEX_MARKET, "\u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0430\u0440\u043a\u0435\u0442"),
        ]:
            product = TrackedProduct(
                user_id=test_user.id,
                marketplace=marketplace,
                external_id=f"label_{marketplace.value}",
                url=f"https://example.com/{marketplace.value}",
                title="Label Test",
                current_price=Decimal("1000"),
                previous_price=Decimal("2000"),
                is_active=True,
            )
            db_session.add(product)
            await db_session.flush()

            log = AlertLog(
                alert_rule_id=1,
                product_id=product.id,
                old_price=Decimal("2000"),
                new_price=Decimal("1000"),
                message_sent=False,
            )

            message = service.format_alert_message(log, product)
            assert expected_label in message
