"""Pydantic schemas for the PriceRadar application."""

from app.schemas.alert import (
    AlertLogResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    RuleType,
)
from app.schemas.product import (
    Marketplace,
    PriceHistoryResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)

__all__ = [
    # Product
    "Marketplace",
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    "PriceHistoryResponse",
    # Alert
    "RuleType",
    "AlertRuleCreate",
    "AlertRuleUpdate",
    "AlertRuleResponse",
    "AlertLogResponse",
]
