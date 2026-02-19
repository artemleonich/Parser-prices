"""Marketplace parsers."""

from app.parsers.base import BaseParser, ParsedProduct
from app.parsers.ozon import OzonParser
from app.parsers.wildberries import WildberriesParser
from app.parsers.yandex_market import YandexMarketParser

PARSERS = {
    "wildberries": WildberriesParser,
    "ozon": OzonParser,
    "yandex_market": YandexMarketParser,
}

__all__ = [
    "BaseParser",
    "ParsedProduct",
    "WildberriesParser",
    "OzonParser",
    "YandexMarketParser",
    "PARSERS",
]
