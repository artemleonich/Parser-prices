from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import structlog

from app.parsers.base import BaseParser, ParsedProduct
from app.parsers.utils import (
    BlockedError,
    NotFoundError,
    ParsingError,
    create_http_client,
    retry_request,
)

logger = structlog.get_logger(__name__)

_WB_API_URL = (
    "https://card.wb.ru/cards/v2/detail"
    "?appType=1&curr=rub&dest=-1257786&spp=30&nm={article_id}"
)

_PRODUCT_ID_RE = re.compile(r"wildberries\.ru/catalog/(\d+)")


class WildberriesParser(BaseParser):
    marketplace: str = "wildberries"

    def extract_product_id(self, url: str) -> str:
        match = _PRODUCT_ID_RE.search(url)
        if not match:
            raise ValueError(f"Cannot extract Wildberries product ID from URL: {url}")
        return match.group(1)

    def build_url(self, product_id: str) -> str:
        return f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx"

    @retry_request
    async def parse_product(self, url_or_id: str) -> ParsedProduct:
        if url_or_id.startswith("http") or "wildberries.ru" in url_or_id:
            product_id = self.extract_product_id(url_or_id)
        else:
            product_id = url_or_id.strip()

        api_url = _WB_API_URL.format(article_id=product_id)
        logger.info("wb: fetching product", product_id=product_id, url=api_url)

        async with create_http_client() as client:
            response = await client.get(api_url)

        if response.status_code == 403:
            raise BlockedError(f"Wildberries blocked the request for product {product_id}")
        if response.status_code == 404:
            raise NotFoundError(f"Wildberries product {product_id} not found")

        response.raise_for_status()

        try:
            data: dict[str, Any] = response.json()
        except Exception as exc:
            raise ParsingError(f"Failed to decode JSON for WB product {product_id}") from exc

        products: list[dict[str, Any]] = (
            data.get("data", {}).get("products", [])
        )
        if not products:
            raise NotFoundError(
                f"Wildberries API returned no products for article {product_id}"
            )

        product: dict[str, Any] = products[0]

        title: str = product.get("name", "")

        # цены в API приходят в копейках
        sale_price_raw: int = product.get("salePriceU", 0)
        price = Decimal(sale_price_raw) / Decimal(100)

        original_price_raw: int = product.get("priceU", 0)
        original_price: Decimal | None = (
            Decimal(original_price_raw) / Decimal(100) if original_price_raw else None
        )

        discount_percent: int | None = product.get("sale")
        if discount_percent is None and original_price and original_price > 0 and price < original_price:
            discount_percent = int(
                ((original_price - price) / original_price * 100)
            )

        in_stock = _check_stock(product)
        image_url = _build_image_url(product_id)

        parsed = ParsedProduct(
            external_id=product_id,
            title=title,
            price=price,
            original_price=original_price,
            discount_percent=discount_percent,
            in_stock=in_stock,
            image_url=image_url,
        )

        logger.info(
            "wb: product parsed",
            product_id=product_id,
            title=title,
            price=str(price),
            in_stock=in_stock,
        )
        return parsed


def _check_stock(product: dict[str, Any]) -> bool:
    total_qty = product.get("totalQuantity")
    if total_qty is not None:
        return int(total_qty) > 0

    for size in product.get("sizes", []):
        for stock in size.get("stocks", []):
            if int(stock.get("qty", 0)) > 0:
                return True
    return False


def _build_image_url(product_id: str) -> str | None:
    """CDN-ссылка на картинку по схеме vol/part/id."""
    try:
        pid = int(product_id)
    except ValueError:
        return None

    vol = pid // 100_000
    part = pid // 1_000

    if vol <= 143:
        basket = "01"
    elif vol <= 287:
        basket = "02"
    elif vol <= 431:
        basket = "03"
    elif vol <= 719:
        basket = "04"
    elif vol <= 1007:
        basket = "05"
    elif vol <= 1061:
        basket = "06"
    elif vol <= 1115:
        basket = "07"
    elif vol <= 1169:
        basket = "08"
    elif vol <= 1313:
        basket = "09"
    elif vol <= 1601:
        basket = "10"
    elif vol <= 1655:
        basket = "11"
    elif vol <= 1919:
        basket = "12"
    elif vol <= 2045:
        basket = "13"
    elif vol <= 2189:
        basket = "14"
    elif vol <= 2405:
        basket = "15"
    elif vol <= 2621:
        basket = "16"
    else:
        basket = "17"

    return (
        f"https://basket-{basket}.wbbasket.ru"
        f"/vol{vol}/part{part}/{pid}/images/big/1.webp"
    )
