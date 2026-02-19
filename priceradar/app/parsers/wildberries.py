"""Wildberries marketplace parser using the public JSON card API."""

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
    """Parser for **Wildberries** product pages.

    Uses the public JSON card API to retrieve product details without
    rendering the page.
    """

    marketplace: str = "wildberries"

    def extract_product_id(self, url: str) -> str:
        """Extract the numeric article ID from a Wildberries URL.

        Args:
            url: Full product URL, e.g.
                ``https://www.wildberries.ru/catalog/12345678/detail.aspx``

        Returns:
            Article ID string.

        Raises:
            ValueError: If the URL does not match the expected pattern.
        """
        match = _PRODUCT_ID_RE.search(url)
        if not match:
            raise ValueError(f"Cannot extract Wildberries product ID from URL: {url}")
        return match.group(1)

    def build_url(self, product_id: str) -> str:
        """Build a canonical Wildberries product URL.

        Args:
            product_id: Numeric article ID.

        Returns:
            Full URL string.
        """
        return f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx"

    @retry_request
    async def parse_product(self, url_or_id: str) -> ParsedProduct:
        """Fetch product data from the Wildberries JSON API.

        Args:
            url_or_id: Full product URL or a bare numeric article ID.

        Returns:
            :class:`ParsedProduct` with normalised data.

        Raises:
            NotFoundError: Product does not exist.
            ParsingError: Unexpected API response structure.
            BlockedError: Request was blocked by the marketplace.
        """
        # Determine the article ID.
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

        # --- title ---
        title: str = product.get("name", "")

        # --- prices (API returns values in kopecks) ---
        sale_price_raw: int = product.get("salePriceU", 0)
        price = Decimal(sale_price_raw) / Decimal(100)

        original_price_raw: int = product.get("priceU", 0)
        original_price: Decimal | None = (
            Decimal(original_price_raw) / Decimal(100) if original_price_raw else None
        )

        # --- discount ---
        discount_percent: int | None = product.get("sale")
        if discount_percent is None and original_price and original_price > 0 and price < original_price:
            discount_percent = int(
                ((original_price - price) / original_price * 100)
            )

        # --- stock ---
        in_stock = _check_stock(product)

        # --- image ---
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_stock(product: dict[str, Any]) -> bool:
    """Return ``True`` when the product has any quantity available."""
    # First, check the top-level totalQuantity field.
    total_qty = product.get("totalQuantity")
    if total_qty is not None:
        return int(total_qty) > 0

    # Fallback: sum over sizes -> stocks -> qty.
    for size in product.get("sizes", []):
        for stock in size.get("stocks", []):
            if int(stock.get("qty", 0)) > 0:
                return True
    return False


def _build_image_url(product_id: str) -> str | None:
    """Construct a product image URL from the Wildberries vol/part/id scheme.

    Wildberries hosts images at a CDN path derived from the article ID:
    * ``vol``  = id // 100_000
    * ``part`` = id // 1_000
    * basket host index depends on the vol range.

    Returns ``None`` if the ID is not numeric.
    """
    try:
        pid = int(product_id)
    except ValueError:
        return None

    vol = pid // 100_000
    part = pid // 1_000

    # Determine basket host index based on vol ranges.
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
