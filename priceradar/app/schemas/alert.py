"""Pydantic schemas for AlertRule and AlertLog."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuleType(str, Enum):
    """Types of alert rules a user can create."""

    PRICE_DROP = "price_drop"
    PRICE_RISE = "price_rise"
    PRICE_BELOW = "price_below"
    PRICE_ABOVE = "price_above"
    BACK_IN_STOCK = "back_in_stock"


# ---------------------------------------------------------------------------
# AlertRule schemas
# ---------------------------------------------------------------------------


class AlertRuleCreate(BaseModel):
    """Schema for creating a new alert rule."""

    product_id: int | None = Field(
        None, description="Tracked-product ID; omit for account-wide rules"
    )
    rule_type: RuleType
    threshold_value: Decimal | None = Field(
        None,
        ge=0,
        decimal_places=2,
        description="Threshold price (required for price_below / price_above rules)",
    )

    @model_validator(mode="after")
    def _validate_threshold(self) -> "AlertRuleCreate":
        """Ensure threshold_value is provided for threshold-based rules."""
        threshold_rules = {RuleType.PRICE_BELOW, RuleType.PRICE_ABOVE}
        if self.rule_type in threshold_rules and self.threshold_value is None:
            raise ValueError(
                f"threshold_value is required for {self.rule_type.value} rules"
            )
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "product_id": 1,
                    "rule_type": "price_below",
                    "threshold_value": "1500.00",
                }
            ]
        },
    )


class AlertRuleUpdate(BaseModel):
    """Schema for updating an existing alert rule."""

    rule_type: RuleType | None = None
    threshold_value: Decimal | None = Field(None, ge=0, decimal_places=2)
    is_active: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"is_active": False}]
        },
    )


class AlertRuleResponse(BaseModel):
    """Full representation of an alert rule returned to the client."""

    id: int
    user_id: int
    product_id: int | None = None
    rule_type: RuleType
    threshold_value: Decimal | None = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# AlertLog schemas
# ---------------------------------------------------------------------------


class AlertLogResponse(BaseModel):
    """Single alert-log entry returned to the client."""

    id: int
    alert_rule_id: int
    product_id: int
    old_price: Decimal
    new_price: Decimal
    message_sent: bool
    sent_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
