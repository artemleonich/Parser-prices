"""Ozon marketplace parser.

Supports two parsing strategies:
1. **Primary** -- mobile Composer API (JSON).
2. **Fallback** -- desktop HTML page with embedded JSON-LD.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from app.parsers.base import BaseParser, ParsedProduct
from app.parsers.utils import (
    BlockedError,
    NotFoundError,
    ParsingError,
    create_http_client,
    get_random_ua,
    retry_request,
)

logger = structlog.get_logger(__name__)

_PRODUCT_ID_RE = re.compile(r"ozon\.ru/product/.*?-(\d+)/?")

_MOBILE_API_URL = (
    "https://api.ozon.ru/composer-api.bx/page/json/v2"
    "?url=/product/{product_id}/"
)

_MOBILE_HEADERS: dict[str, str] = {
    "x-o3-app-name": "ozonapp_android",
    "x-o3-app-version": "17.35.0",
}

_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)


class OzonParser(BaseParser):
    """Parser for **Ozon** product pages."""

    marketplace: str = "ozon"

    def extract_product_id(self, url: str) -> str:
        """Extract the numeric product ID from an Ozon URL.

        Args:
            url: Full product URL, e.g.
                ``https://www.ozon.ru/product/some-name-123456789/``

        Returns:
            Product ID string.

        Raises:
            ValueError: If the URL does not match the expected pattern.
        """
        match = _PRODUCT_ID_RE.search(url)
        if not match:
            raise ValueError(f"Cannot extract Ozon product ID from URL: {url}")
        return match.group(1)

    def build_url(self, product_id: str) -> str:
        """Build a canonical Ozon product URL.

        Args:
            product_id: Numeric product ID.

        Returns:
            Full URL string.
        """
        return f"https://www.ozon.ru/product/{product_id}/"

    @retry_request
    async def parse_product(self, url_or_id: str) -> ParsedProduct:
        """Fetch product data from Ozon.

        Tries the mobile Composer API first; falls back to scraping the
        desktop HTML page for JSON-LD on failure.

        Args:
            url_or_id: Full product URL or a bare numeric product ID.

        Returns:
            :class:`ParsedProduct` with normalised data.

        Raises:
            NotFoundError: Product does not exist.
            ParsingError: Both strategies failed to extract data.
            BlockedError: Request was blocked (HTTP 403).
        """
        if url_or_id.startswith("http") or "ozon.ru" in url_or_id:
            product_id = self.extract_product_id(url_or_id)
        else:
            product_id = url_or_id.strip()

        logger.info("ozon: fetching product", product_id=product_id)

        # ---- Strategy 1: Mobile Composer API ---------------------------------
        try:
            result = await self._parse_via_api(product_id)
            logger.info("ozon: parsed via mobile API", product_id=product_id)
            return result
        except NotFoundError:
            raise
        except Exception as exc:
            logger.warning(
                "ozon: mobile API failed, falling back to HTML",
                product_id=product_id,
                error=str(exc),
            )

        # ---- Strategy 2: HTML + JSON-LD --------------------------------------
        result = await self._parse_via_html(product_id)
        logger.info("ozon: parsed via HTML fallback", product_id=product_id)
        return result

    # ------------------------------------------------------------------
    # Strategy 1 -- mobile API
    # ------------------------------------------------------------------

    async def _parse_via_api(self, product_id: str) -> ParsedProduct:
        """Fetch product information from the Ozon mobile Composer API."""
        api_url = _MOBILE_API_URL.format(product_id=product_id)

        mobile_ua = (
            "Mozilla/5.0 (Linux; Android 14; SM-S918B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Mobile Safari/537.36"
        )
        headers: dict[str, str] = {
            "User-Agent": mobile_ua,
            **_MOBILE_HEADERS,
        }

        async with create_http_client(headers=headers) as client:
            response = await client.get(api_url)

        if response.status_code == 403:
            raise BlockedError(f"Ozon blocked the API request for product {product_id}")
        if response.status_code == 404:
            raise NotFoundError(f"Ozon product {product_id} not found via API")

        response.raise_for_status()

        try:
            payload: dict[str, Any] = response.json()
        except Exception as exc:
            raise ParsingError(f"Failed to decode Ozon API JSON for product {product_id}") from exc

        return self._extract_from_api_payload(payload, product_id)

    def _extract_from_api_payload(
        self,
        payload: dict[str, Any],
        product_id: str,
    ) -> ParsedProduct:
        """Walk the Composer API widget tree and extract product fields."""
        title: str = ""
        price: Decimal | None = None
        original_price: Decimal | None = None
        image_url: str | None = None
        in_stock: bool = True

        # The Composer API returns a nested widget state map.
        widget_states: dict[str, Any] = payload.get("widgetStates", {})

        for _key, raw_value in widget_states.items():
            # Values may be JSON-encoded strings.
            if isinstance(raw_value, str):
                try:
                    value = json.loads(raw_value)
                except (json.JSONDecodeError, TypeError):
                    continue
            else:
                value = raw_value

            if not isinstance(value, dict):
                continue

            # Look for webPrice / price data.
            web_price = value.get("webPrice") or value.get("price")
            if isinstance(web_price, dict):
                price = price or _parse_price_string(web_price.get("price"))
                original_price = original_price or _parse_price_string(
                    web_price.get("originalPrice")
                )

            # Title.
            if not title:
                title = value.get("title", "") or value.get("productTitle", "")

            # Image.
            if not image_url:
                covers = value.get("coverImage") or value.get("images") or value.get("gallery")
                if isinstance(covers, list) and covers:
                    first = covers[0]
                    image_url = first if isinstance(first, str) else first.get("src") or first.get("url")
                elif isinstance(covers, str):
                    image_url = covers

            # Out-of-stock signal.
            if value.get("isOutOfStock") is True:
                in_stock = False

        if price is None:
            raise ParsingError(
                f"Could not extract price from Ozon API response for product {product_id}"
            )

        discount_percent = _calc_discount(price, original_price)

        return ParsedProduct(
            external_id=product_id,
            title=title,
            price=price,
            original_price=original_price,
            discount_percent=discount_percent,
            in_stock=in_stock,
            image_url=image_url,
        )

    # ------------------------------------------------------------------
    # Strategy 2 -- HTML + JSON-LD
    # ------------------------------------------------------------------

    async def _parse_via_html(self, product_id: str) -> ParsedProduct:
        """Scrape the desktop HTML page and extract JSON-LD product data."""
        page_url = self.build_url(product_id)

        async with create_http_client() as client:
            response = await client.get(page_url)

        if response.status_code == 403:
            raise BlockedError(f"Ozon blocked the HTML request for product {product_id}")
        if response.status_code == 404:
            raise NotFoundError(f"Ozon product {product_id} not found")

        response.raise_for_status()
        html = response.text

        json_ld_blocks = _JSON_LD_RE.findall(html)
        if not json_ld_blocks:
            raise ParsingError(
                f"No JSON-LD blocks found on Ozon page for product {product_id}"
            )

        for block in json_ld_blocks:
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue

            # JSON-LD may be a list or a single object.
            items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Product", "IndividualProduct"):
                    return self._extract_from_json_ld(item, product_id)

        raise ParsingError(
            f"No Product JSON-LD found on Ozon page for product {product_id}"
        )

    def _extract_from_json_ld(
        self,
        item: dict[str, Any],
        product_id: str,
    ) -> ParsedProduct:
        """Build a :class:`ParsedProduct` from a JSON-LD ``Product`` object."""
        title: str = item.get("name", "")

        offers: dict[str, Any] = item.get("offers", {})
        price = _parse_price_string(offers.get("price"))
        if price is None:
            price = _parse_price_string(offers.get("lowPrice"))
        if price is None:
            raise ParsingError(
                f"Could not extract price from Ozon JSON-LD for product {product_id}"
            )

        original_price = _parse_price_string(offers.get("highPrice"))

        availability: str = offers.get("availability", "")
        in_stock = "InStock" in availability if availability else True

        image_url: str | None = None
        image_raw = item.get("image")
        if isinstance(image_raw, list) and image_raw:
            image_url = image_raw[0]
        elif isinstance(image_raw, str):
            image_url = image_raw

        discount_percent = _calc_discount(price, original_price)

        return ParsedProduct(
            external_id=product_id,
            title=title,
            price=price,
            original_price=original_price,
            discount_percent=discount_percent,
            in_stock=in_stock,
            image_url=image_url,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PRICE_CLEAN_RE = re.compile(r"[^\d.,]")


def _parse_price_string(raw: Any) -> Decimal | None:
    """Best-effort conversion of a price value to :class:`Decimal`.

    Handles strings like ``"1 234,56 ₽"`` as well as plain numeric types.
    Returns ``None`` when the value is missing or unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    if not isinstance(raw, str):
        return None

    cleaned = _PRICE_CLEAN_RE.sub("", raw).replace(",", ".")
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _calc_discount(
    price: Decimal,
    original_price: Decimal | None,
) -> int | None:
    """Calculate integer discount percentage, or ``None``."""
    if original_price and original_price > 0 and price < original_price:
        return int((original_price - price) / original_price * 100)
    return None
