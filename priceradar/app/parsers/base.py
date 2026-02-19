"""Abstract base parser and common data structures for marketplace parsers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ParsedProduct:
    """Normalized product data returned by every parser."""

    external_id: str
    title: str
    price: Decimal
    original_price: Decimal | None = None
    discount_percent: int | None = None
    in_stock: bool = True
    image_url: str | None = None


# Mapping of domain substring -> marketplace key used by detect_marketplace.
_DOMAIN_MAP: dict[str, str] = {
    "wildberries.ru": "wildberries",
    "wb.ru": "wildberries",
    "ozon.ru": "ozon",
    "market.yandex.ru": "yandex_market",
}


class BaseParser(ABC):
    """Abstract base class that every marketplace parser must implement."""

    marketplace: ClassVar[str]

    @abstractmethod
    async def parse_product(self, url_or_id: str) -> ParsedProduct:
        """Fetch and parse product information from the marketplace.

        Args:
            url_or_id: Full product URL or marketplace-specific product ID.

        Returns:
            A :class:`ParsedProduct` with normalised data.
        """

    @abstractmethod
    def extract_product_id(self, url: str) -> str:
        """Extract the marketplace-specific product ID from a URL.

        Args:
            url: Full product URL.

        Returns:
            Product ID string.

        Raises:
            ValueError: If the URL does not match the expected pattern.
        """

    @abstractmethod
    def build_url(self, product_id: str) -> str:
        """Build a canonical product URL from a product ID.

        Args:
            product_id: Marketplace-specific product ID.

        Returns:
            Full product URL.
        """

    @staticmethod
    def detect_marketplace(url: str) -> str | None:
        """Detect the marketplace from a product URL.

        The method checks well-known domain substrings against the provided URL.

        Args:
            url: Full product URL.

        Returns:
            Marketplace key string (e.g. ``"wildberries"``) or ``None`` if
            the domain is not recognised.
        """
        url_lower = url.lower()
        for domain, marketplace in _DOMAIN_MAP.items():
            if re.search(rf"(?:^https?://(?:www\.)?|://)?" + re.escape(domain), url_lower):
                return marketplace
        return None
