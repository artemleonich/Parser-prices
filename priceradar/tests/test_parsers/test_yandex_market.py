import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.parsers.yandex_market import YandexMarketParser
from app.parsers.utils import BlockedError, NotFoundError, ParsingError


def _make_yandex_html_with_json_ld(
    title: str = "Yandex Test Product",
    price: str = "15990",
    high_price: str | None = "19990",
    availability: str = "https://schema.org/InStock",
    image_url: str = "https://avatars.mds.yandex.net/product.jpg",
    currency: str = "RUB",
) -> str:
    offers: dict = {
        "@type": "Offer",
        "price": price,
        "priceCurrency": currency,
        "availability": availability,
    }
    if high_price is not None:
        offers["highPrice"] = high_price

    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "image": [image_url],
        "offers": offers,
    })
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="application/ld+json">{json_ld}</script>
    </head>
    <body><h1>{title}</h1></body>
    </html>
    """


def _make_yandex_html_with_list_json_ld(
    title: str = "Yandex List Product",
    price: str = "9990",
) -> str:
    json_ld = json.dumps([
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [],
        },
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": title,
            "image": "https://avatars.mds.yandex.net/list_product.jpg",
            "offers": {
                "@type": "Offer",
                "price": price,
                "priceCurrency": "RUB",
                "availability": "https://schema.org/InStock",
            },
        },
    ])
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="application/ld+json">{json_ld}</script>
    </head>
    <body><h1>{title}</h1></body>
    </html>
    """


def _build_httpx_response(
    text_body: str,
    status_code: int = 200,
    url: str = "https://market.yandex.ru/product/123456",
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        text=text_body,
        request=httpx.Request("GET", url),
    )


def _mock_client(response: httpx.Response) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestExtractProductId:

    def setup_method(self) -> None:
        self.parser = YandexMarketParser()

    def test_standard_url_with_slug(self) -> None:
        url = "https://market.yandex.ru/product--smartphone-example/123456"
        assert self.parser.extract_product_id(url) == "123456"

    def test_url_without_slug(self) -> None:
        url = "https://market.yandex.ru/product/789012"
        assert self.parser.extract_product_id(url) == "789012"

    def test_url_with_query_params(self) -> None:
        url = "https://market.yandex.ru/product--some-product/345678?sku=111&cpc=abc"
        assert self.parser.extract_product_id(url) == "345678"

    def test_url_with_trailing_slash(self) -> None:
        url = "https://market.yandex.ru/product--gadget/654321/"
        assert self.parser.extract_product_id(url) == "654321"

    def test_url_with_fragment(self) -> None:
        url = "https://market.yandex.ru/product--item/111222#spec"
        assert self.parser.extract_product_id(url) == "111222"

    def test_invalid_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract Yandex Market product ID"):
            self.parser.extract_product_id("https://example.com/product/123")

    def test_yandex_non_market_url_raises(self) -> None:
        with pytest.raises(ValueError):
            self.parser.extract_product_id("https://yandex.ru/product/123")


class TestBuildUrl:

    def setup_method(self) -> None:
        self.parser = YandexMarketParser()

    def test_build_url_returns_canonical_format(self) -> None:
        url = self.parser.build_url("123456")
        assert url == "https://market.yandex.ru/product/123456"

    def test_build_url_preserves_product_id(self) -> None:
        url = self.parser.build_url("999888")
        assert "999888" in url
        assert url.startswith("https://market.yandex.ru/product/")


class TestParseProduct:

    def setup_method(self) -> None:
        self.parser = YandexMarketParser()

    @pytest.mark.asyncio
    async def test_parse_product_success(self) -> None:
        html = _make_yandex_html_with_json_ld()
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://market.yandex.ru/product--smartphone-example/123456"
            )

        assert result.external_id == "123456"
        assert result.title == "Yandex Test Product"
        assert result.price == Decimal("15990")
        assert result.original_price == Decimal("19990")
        assert result.in_stock is True
        assert result.image_url == "https://avatars.mds.yandex.net/product.jpg"

    @pytest.mark.asyncio
    async def test_parse_product_bare_id(self) -> None:
        html = _make_yandex_html_with_json_ld()
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product("123456")

        assert result.external_id == "123456"

    @pytest.mark.asyncio
    async def test_parse_product_out_of_stock(self) -> None:
        html = _make_yandex_html_with_json_ld(
            availability="https://schema.org/OutOfStock"
        )
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://market.yandex.ru/product/123456"
            )

        assert result.in_stock is False

    @pytest.mark.asyncio
    async def test_parse_product_discount_calculated(self) -> None:
        html = _make_yandex_html_with_json_ld(
            price="5000", high_price="10000",
        )
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://market.yandex.ru/product/123456"
            )

        assert result.discount_percent == 50

    @pytest.mark.asyncio
    async def test_parse_product_no_discount_when_no_high_price(self) -> None:
        html = _make_yandex_html_with_json_ld(
            price="5000", high_price=None,
        )
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://market.yandex.ru/product/123456"
            )

        assert result.discount_percent is None
        assert result.original_price is None

    @pytest.mark.asyncio
    async def test_parse_product_json_ld_as_list(self) -> None:
        html = _make_yandex_html_with_list_json_ld()
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://market.yandex.ru/product/123456"
            )

        assert result.title == "Yandex List Product"
        assert result.price == Decimal("9990")

    @pytest.mark.asyncio
    async def test_parse_product_blocked_raises(self) -> None:
        mock_resp = httpx.Response(
            status_code=403,
            request=httpx.Request("GET", "https://market.yandex.ru/product/123456"),
        )
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            with pytest.raises(BlockedError):
                await self.parser.parse_product(
                    "https://market.yandex.ru/product/123456"
                )

    @pytest.mark.asyncio
    async def test_parse_product_not_found_raises(self) -> None:
        mock_resp = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://market.yandex.ru/product/123456"),
        )
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            with pytest.raises(NotFoundError):
                await self.parser.parse_product(
                    "https://market.yandex.ru/product/123456"
                )

    @pytest.mark.asyncio
    async def test_parse_product_no_json_ld_raises(self) -> None:
        html = "<html><head></head><body>No JSON-LD</body></html>"
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            with pytest.raises(ParsingError, match="No JSON-LD blocks found"):
                await self.parser.parse_product(
                    "https://market.yandex.ru/product/123456"
                )

    @pytest.mark.asyncio
    async def test_parse_product_json_ld_without_product_type_raises(self) -> None:
        json_ld = json.dumps({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [],
        })
        html = f"""
        <html>
        <head>
            <script type="application/ld+json">{json_ld}</script>
        </head>
        <body></body>
        </html>
        """
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            with pytest.raises(ParsingError, match="No Product JSON-LD found"):
                await self.parser.parse_product(
                    "https://market.yandex.ru/product/123456"
                )

    @pytest.mark.asyncio
    async def test_parse_product_image_as_string(self) -> None:
        json_ld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Single Image Product",
            "image": "https://avatars.mds.yandex.net/single.jpg",
            "offers": {
                "@type": "Offer",
                "price": "1000",
                "priceCurrency": "RUB",
                "availability": "https://schema.org/InStock",
            },
        })
        html = f"""
        <html>
        <head>
            <script type="application/ld+json">{json_ld}</script>
        </head>
        <body></body>
        </html>
        """
        mock_resp = _build_httpx_response(html)
        client = _mock_client(mock_resp)

        with patch("app.parsers.yandex_market.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://market.yandex.ru/product/123456"
            )

        assert result.image_url == "https://avatars.mds.yandex.net/single.jpg"
