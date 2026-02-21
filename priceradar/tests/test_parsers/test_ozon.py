import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.parsers.ozon import OzonParser
from app.parsers.utils import BlockedError, NotFoundError, ParsingError


def _make_ozon_api_response(
    title: str = "Ozon Test Product",
    price: str = "4 990 ₽",
    original_price: str = "7 990 ₽",
    is_out_of_stock: bool = False,
    image_url: str = "https://cdn.ozon.ru/image.jpg",
) -> dict:
    price_widget = json.dumps({
        "webPrice": {
            "price": price,
            "originalPrice": original_price,
        }
    })
    title_widget = json.dumps({
        "title": title,
    })
    gallery_widget = json.dumps({
        "coverImage": [image_url],
    })
    stock_widget = json.dumps({
        "isOutOfStock": is_out_of_stock,
    })
    return {
        "widgetStates": {
            "webPrice-123": price_widget,
            "webProductHeading-456": title_widget,
            "webGallery-789": gallery_widget,
            "webOutOfStock-000": stock_widget,
        }
    }


def _make_ozon_html_with_json_ld(
    title: str = "Ozon HTML Product",
    price: str = "3990",
    high_price: str = "5990",
    availability: str = "https://schema.org/InStock",
    image_url: str = "https://cdn.ozon.ru/html_image.jpg",
) -> str:
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "image": [image_url],
        "offers": {
            "@type": "Offer",
            "price": price,
            "highPrice": high_price,
            "priceCurrency": "RUB",
            "availability": availability,
        },
    })
    return f"""
    <html>
    <head>
        <script type="application/ld+json">{json_ld}</script>
    </head>
    <body><h1>{title}</h1></body>
    </html>
    """


def _build_httpx_response(
    json_body: dict | None = None,
    text_body: str | None = None,
    status_code: int = 200,
    url: str = "https://api.ozon.ru/composer-api.bx/page/json/v2",
) -> httpx.Response:
    kwargs: dict = {
        "status_code": status_code,
        "request": httpx.Request("GET", url),
    }
    if json_body is not None:
        kwargs["json"] = json_body
    if text_body is not None:
        kwargs["text"] = text_body
    return httpx.Response(**kwargs)


def _mock_client(response: httpx.Response) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestExtractProductId:

    def setup_method(self) -> None:
        self.parser = OzonParser()

    def test_standard_url(self) -> None:
        url = "https://www.ozon.ru/product/some-product-name-123456789/"
        assert self.parser.extract_product_id(url) == "123456789"

    def test_url_without_trailing_slash(self) -> None:
        url = "https://www.ozon.ru/product/product-name-987654321"
        assert self.parser.extract_product_id(url) == "987654321"

    def test_url_with_query_params(self) -> None:
        url = "https://www.ozon.ru/product/test-item-555555555/?sh=abc123"
        assert self.parser.extract_product_id(url) == "555555555"

    def test_short_slug(self) -> None:
        url = "https://ozon.ru/product/x-111111111/"
        assert self.parser.extract_product_id(url) == "111111111"

    def test_invalid_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract Ozon product ID"):
            self.parser.extract_product_id("https://example.com/product/123")

    def test_url_without_product_id_raises(self) -> None:
        with pytest.raises(ValueError):
            self.parser.extract_product_id("https://www.ozon.ru/category/electronics/")


class TestBuildUrl:

    def setup_method(self) -> None:
        self.parser = OzonParser()

    def test_build_url_returns_canonical_format(self) -> None:
        url = self.parser.build_url("123456789")
        assert url == "https://www.ozon.ru/product/123456789/"

    def test_build_url_preserves_product_id(self) -> None:
        url = self.parser.build_url("999888777")
        assert "999888777" in url


class TestParseProductViaApi:

    def setup_method(self) -> None:
        self.parser = OzonParser()

    @pytest.mark.asyncio
    async def test_parse_product_via_api_success(self) -> None:
        api_json = _make_ozon_api_response()
        mock_resp = _build_httpx_response(json_body=api_json)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://www.ozon.ru/product/test-item-123456789/"
            )

        assert result.external_id == "123456789"
        assert result.title == "Ozon Test Product"
        assert result.price == Decimal("4990")
        assert result.original_price == Decimal("7990")
        assert result.in_stock is True
        assert result.image_url == "https://cdn.ozon.ru/image.jpg"

    @pytest.mark.asyncio
    async def test_parse_product_via_api_out_of_stock(self) -> None:
        api_json = _make_ozon_api_response(is_out_of_stock=True)
        mock_resp = _build_httpx_response(json_body=api_json)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            result = await self.parser.parse_product(
                "https://www.ozon.ru/product/test-item-123456789/"
            )

        assert result.in_stock is False

    @pytest.mark.asyncio
    async def test_parse_product_via_api_bare_id(self) -> None:
        api_json = _make_ozon_api_response()
        mock_resp = _build_httpx_response(json_body=api_json)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            result = await self.parser.parse_product("123456789")

        assert result.external_id == "123456789"

    @pytest.mark.asyncio
    async def test_parse_product_blocked_raises(self) -> None:
        mock_resp = _build_httpx_response(json_body={}, status_code=403)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            with pytest.raises(BlockedError):
                await self.parser.parse_product("123456789")

    @pytest.mark.asyncio
    async def test_parse_product_not_found_raises(self) -> None:
        mock_resp = _build_httpx_response(json_body={}, status_code=404)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            with pytest.raises(NotFoundError):
                await self.parser.parse_product("123456789")


class TestParseProductViaHtmlFallback:

    def setup_method(self) -> None:
        self.parser = OzonParser()

    @pytest.mark.asyncio
    async def test_fallback_to_html_on_api_failure(self) -> None:
        api_resp = _build_httpx_response(json_body={"widgetStates": {}}, status_code=200)
        html_body = _make_ozon_html_with_json_ld()
        html_resp = _build_httpx_response(
            text_body=html_body,
            status_code=200,
            url="https://www.ozon.ru/product/123456789/",
        )

        call_count = 0

        def _fake_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_client(api_resp)
            else:
                return _mock_client(html_resp)

        with patch("app.parsers.ozon.create_http_client", side_effect=_fake_client):
            result = await self.parser.parse_product(
                "https://www.ozon.ru/product/test-item-123456789/"
            )

        assert result.external_id == "123456789"
        assert result.title == "Ozon HTML Product"
        assert result.price == Decimal("3990")
        assert result.original_price == Decimal("5990")
        assert result.in_stock is True
        assert result.image_url == "https://cdn.ozon.ru/html_image.jpg"

    @pytest.mark.asyncio
    async def test_html_json_ld_out_of_stock(self) -> None:
        html_body = _make_ozon_html_with_json_ld(
            availability="https://schema.org/OutOfStock"
        )
        html_resp = _build_httpx_response(
            text_body=html_body,
            status_code=200,
            url="https://www.ozon.ru/product/123456789/",
        )

        api_resp = _build_httpx_response(
            json_body={"widgetStates": {}}, status_code=200,
        )

        call_count = 0

        def _fake_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_client(api_resp)
            else:
                return _mock_client(html_resp)

        with patch("app.parsers.ozon.create_http_client", side_effect=_fake_client):
            result = await self.parser.parse_product(
                "https://www.ozon.ru/product/test-item-123456789/"
            )

        assert result.in_stock is False

    @pytest.mark.asyncio
    async def test_html_no_json_ld_raises(self) -> None:
        html_body = "<html><head></head><body>No JSON-LD here</body></html>"
        html_resp = _build_httpx_response(
            text_body=html_body,
            status_code=200,
            url="https://www.ozon.ru/product/123456789/",
        )

        api_resp = _build_httpx_response(
            json_body={"widgetStates": {}}, status_code=200,
        )

        call_count = 0

        def _fake_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_client(api_resp)
            else:
                return _mock_client(html_resp)

        with patch("app.parsers.ozon.create_http_client", side_effect=_fake_client):
            with pytest.raises(ParsingError, match="No JSON-LD blocks found"):
                await self.parser.parse_product(
                    "https://www.ozon.ru/product/test-item-123456789/"
                )


class TestDiscountCalculation:

    def setup_method(self) -> None:
        self.parser = OzonParser()

    @pytest.mark.asyncio
    async def test_discount_percent_calculated(self) -> None:
        api_json = _make_ozon_api_response(
            price="5 000 ₽", original_price="10 000 ₽",
        )
        mock_resp = _build_httpx_response(json_body=api_json)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            result = await self.parser.parse_product("123456789")

        assert result.discount_percent == 50

    @pytest.mark.asyncio
    async def test_no_discount_when_prices_equal(self) -> None:
        api_json = _make_ozon_api_response(
            price="5 000 ₽", original_price="5 000 ₽",
        )
        mock_resp = _build_httpx_response(json_body=api_json)
        client = _mock_client(mock_resp)

        with patch("app.parsers.ozon.create_http_client", return_value=client):
            result = await self.parser.parse_product("123456789")

        assert result.discount_percent is None
