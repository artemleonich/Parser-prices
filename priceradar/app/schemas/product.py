from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Marketplace(str, Enum):

    WILDBERRIES = "wildberries"
    OZON = "ozon"
    YANDEX_MARKET = "yandex_market"


class ProductCreate(BaseModel):

    url: HttpUrl = Field(..., description="Product page URL on the marketplace")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"url": "https://www.wildberries.ru/catalog/12345678/detail.aspx"}
            ]
        },
    )


class ProductUpdate(BaseModel):

    title: str | None = Field(None, max_length=500)
    is_active: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"title": "Updated product title", "is_active": False}]
        },
    )


class ProductResponse(BaseModel):

    id: int
    user_id: int
    marketplace: Marketplace
    external_id: str
    url: str
    title: str
    current_price: Decimal | None = None
    previous_price: Decimal | None = None
    price_updated_at: datetime | None = None
    image_url: str | None = None
    is_active: bool
    parse_errors_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceHistoryResponse(BaseModel):

    id: int
    product_id: int
    price: Decimal
    original_price: Decimal | None = None
    discount_percent: int | None = None
    in_stock: bool
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)
