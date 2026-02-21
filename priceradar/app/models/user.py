import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, func

# SQLite only auto-generates ROWID for exact INTEGER PRIMARY KEY columns.
# BigInteger renders as BIGINT, which breaks autoincrement in SQLite (tests).
BigIntPK = BigInteger().with_variant(Integer, "sqlite")
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


PLAN_LIMITS = {
    SubscriptionPlan.FREE: {
        "max_products": 5,
        "max_alerts": 3,
        "max_marketplaces": 1,
        "history_days": 7,
        "csv_export": False,
    },
    SubscriptionPlan.BASIC: {
        "max_products": 50,
        "max_alerts": 20,
        "max_marketplaces": 3,
        "history_days": 30,
        "csv_export": True,
    },
    SubscriptionPlan.PRO: {
        "max_products": 200,
        "max_alerts": 999999,
        "max_marketplaces": 3,
        "history_days": 90,
        "csv_export": True,
    },
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan), default=SubscriptionPlan.FREE, nullable=False
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_tracked_products: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tracked_products: Mapped[list["TrackedProduct"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    alert_rules: Mapped[list["AlertRule"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def plan_limits(self) -> dict:
        return PLAN_LIMITS[self.subscription_plan]

    @property
    def is_subscription_active(self) -> bool:
        if self.subscription_plan == SubscriptionPlan.FREE:
            return True
        if self.subscription_expires_at is None:
            return False
        return self.subscription_expires_at > datetime.now(
            tz=self.subscription_expires_at.tzinfo
        )
