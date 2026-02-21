import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    func,
)

BigIntPK = BigInteger().with_variant(Integer, "sqlite")
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RuleType(str, enum.Enum):
    PRICE_DROP = "price_drop"
    PRICE_RISE = "price_rise"
    PRICE_BELOW = "price_below"
    PRICE_ABOVE = "price_above"
    BACK_IN_STOCK = "back_in_stock"


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tracked_products.id", ondelete="CASCADE"), nullable=True
    )
    rule_type: Mapped[RuleType] = mapped_column(Enum(RuleType), nullable=False)
    threshold_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="alert_rules")  # noqa: F821
    product: Mapped["TrackedProduct | None"] = relationship(  # noqa: F821
        back_populates="alert_rules"
    )
    logs: Mapped[list["AlertLog"]] = relationship(
        back_populates="alert_rule", cascade="all, delete-orphan"
    )


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    alert_rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tracked_products.id", ondelete="CASCADE"), nullable=False
    )
    old_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    message_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    alert_rule: Mapped["AlertRule"] = relationship(back_populates="logs")
    product: Mapped["TrackedProduct"] = relationship()  # noqa: F821
