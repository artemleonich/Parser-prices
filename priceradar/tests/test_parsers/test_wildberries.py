from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.parsers.wildberries import WildberriesParser


def _make_wb_api_response(
    product_id: int = 12345,
    name: str = "Test Product",
    sale_price_u: int = 849000,
    price_u: int = 1299000,
    sale: int = 35,
    total_quantity: int = 10,
) -> dict:
    return {
        "data": {
            "products": [
                {
                    "id": product_id,
                    "name": name,
                    "salePriceU": sale_price_u,
                    "priceU": price_u,
                    "sale": sale,
                    "totalQuantity": total_quantity,
                }
            ]
        }
    }


def _build_httpx_response(json_body: dict, status_code: int = 200) -> httpx.Response:
    response = httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("GET", "https://card.wb.ru/cards/v2/detail"),
    )
    return response


class TestExtractProductId:

    def setup_method(self) -> None:
        self.parser = WildberriesParser()

    def test_standard_url(self) -> None:
        url = "https://www.wildberries.ru/catalog/12345678/detail.aspx"
        assert self.parser.extract_product_id(url) == "12345678"

    def test_url_with_query_params(self) -> None:
        url = "https://www.wildberries.ru/catalog/87654321/detail.aspx?targetUrl=GP"
        assert self.parser.extract_product_id(url) == "87654321"

    def test_mobile_url(self) -> None:
        url = "https://wildberries.ru/catalog/99887766/detail.aspx"
        assert self.parser.extract_product_id(url) == "99887766"

    def test_url_without_detail(self) -> None:
        url = "https://www.wildberries.ru/catalog/55555555"
        assert self.parser.extract_product_id(url) == "55555555"

    def test_invalid_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract Wildberries product ID"):
            self.parser.extract_product_id("https://example.com/product/123")

    def test_url_with_fragment(self) -> None:
        url = "https://www.wildberries.ru/catalog/11223344/detail.aspx#reviews"
        assert self.parser.extract_product_id(url) == "11223344"


class TestBuildUrl:

    def setup_method(self) -> None:
        self.parser = WildberriesParser()

    def test_build_url_returns_canonical_format(self) -> None:
        url = self.parser.build_url("12345678")
        assert url == "https://www.wildberries.ru/catalog/12345678/detail.aspx"

    def test_build_url_preserves_product_id(self) -> None:
        url = self.parser.build_url("99999999")
        assert "99999999" in url


class TestParseProduct:

    def setup_method(self) -> None:
        self.parser = WildberriesParser()

    @pytest.mark.asyncio
    async def test_parse_product_from_url(self) -> None:
        api_json = _make_wb_api_response()
        mock_response = _build_httpx_response(api_json)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            result = await self.parser.parse_product(
                "https://www.wildberries.ru/catalog/12345/detail.aspx"
            )

        assert result.external_id == "12345"
        assert result.title == "Test Product"
        assert result.price == Decimal("8490.00")
        assert result.original_price == Decimal("12990.00")
        assert result.discount_percent == 35
        assert result.in_stock is True

    @pytest.mark.asyncio
    async def test_parse_product_from_bare_id(self) -> None:
        api_json = _make_wb_api_response(product_id=999)
        mock_response = _build_httpx_response(api_json)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            result = await self.parser.parse_product("999")

        assert result.external_id == "999"
        assert result.price == Decimal("8490.00")

    @pytest.mark.asyncio
    async def test_parse_product_out_of_stock(self) -> None:
        api_json = _make_wb_api_response(total_quantity=0)
        mock_response = _build_httpx_response(api_json)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            result = await self.parser.parse_product("12345")

        assert result.in_stock is False

    @pytest.mark.asyncio
    async def test_parse_product_blocked_raises(self) -> None:
        mock_response = httpx.Response(
            status_code=403,
            request=httpx.Request("GET", "https://card.wb.ru/cards/v2/detail"),
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        from app.parsers.utils import BlockedError

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            with pytest.raises(BlockedError):
                await self.parser.parse_product("12345")

    @pytest.mark.asyncio
    async def test_parse_product_not_found_raises(self) -> None:
        mock_response = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://card.wb.ru/cards/v2/detail"),
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        from app.parsers.utils import NotFoundError

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            with pytest.raises(NotFoundError):
                await self.parser.parse_product("12345")

    @pytest.mark.asyncio
    async def test_parse_product_empty_products_raises(self) -> None:
        api_json = {"data": {"products": []}}
        mock_response = _build_httpx_response(api_json)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        from app.parsers.utils import NotFoundError

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            with pytest.raises(NotFoundError):
                await self.parser.parse_product("12345")

    @pytest.mark.asyncio
    async def test_parse_product_image_url_generated(self) -> None:
        api_json = _make_wb_api_response(product_id=12345)
        mock_response = _build_httpx_response(api_json)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.wildberries.create_http_client", return_value=mock_client):
            result = await self.parser.parse_product("12345")

        assert result.image_url is not None
        assert "wbbasket.ru" in result.image_url
