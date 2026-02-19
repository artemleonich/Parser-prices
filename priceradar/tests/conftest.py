"""Shared test fixtures for the PriceRadar test suite.

Uses an async in-memory SQLite database so tests run without any
external services.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.user import SubscriptionPlan, User
from app.models.product import Marketplace, TrackedProduct


# ---------------------------------------------------------------------------
# Event loop fixture (session-scoped so the engine can be reused)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Async SQLite engine & session
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_session():
    """Yield an async SQLAlchemy session backed by an in-memory SQLite DB.

    A fresh database is created for every test so that tests are fully
    isolated from each other.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Domain-object fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def test_user(db_session: AsyncSession) -> User:
    """Create and return a persisted test User with the FREE plan."""
    user = User(
        telegram_id=123456,
        first_name="Test",
        subscription_plan=SubscriptionPlan.FREE,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture()
async def test_product(
    db_session: AsyncSession,
    test_user: User,
) -> TrackedProduct:
    """Create and return a persisted TrackedProduct on Wildberries."""
    product = TrackedProduct(
        user_id=test_user.id,
        marketplace=Marketplace.WILDBERRIES,
        external_id="12345678",
        url="https://www.wildberries.ru/catalog/12345678/detail.aspx",
        title="Test Product",
        current_price=Decimal("8490.00"),
        previous_price=Decimal("12990.00"),
        price_updated_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()
    return product
