from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from resham.db.models.brand import Brand
from resham.db.models.product import Product
from resham.db.models.product_variant import ProductVariant
from resham.extension.service import ExtensionSearchError, ExtensionSearchService
from resham.schemas.extension import ExtensionIntent
from resham.search.service import SearchResult


def _query_result(*, first=None, all_rows=None, scalar=None):
    result = MagicMock()
    result.scalars.return_value.first.return_value = first
    result.scalars.return_value.all.return_value = all_rows or []
    result.scalar_one.return_value = scalar
    return result


@pytest.mark.asyncio
async def test_search_scopes_shared_search_to_active_store_and_maps_contract():
    brand_id = uuid4()
    product_id = uuid4()
    brand = Brand(
        id=brand_id,
        name="Outfitters",
        slug="outfitters",
        domain="outfitters.com.pk",
        department="unisex",
    )
    product = Product(
        id=product_id,
        brand_id=brand_id,
        external_id="42",
        composite_key="outfitters:42",
        title="Blue Core Kurta",
        min_price=Decimal("4500"),
        currency="PKR",
        primary_image_url="https://cdn.example/primary.jpg",
        product_url="https://outfitters.com.pk/products/blue-core-kurta",
        department="men",
    )
    variant = ProductVariant(
        product_id=product_id,
        external_variant_id="v1",
        color="Blue",
        size="M",
        price=Decimal("4500"),
        available=True,
        image_url="https://cdn.example/blue.jpg",
    )
    session = AsyncMock()
    session.execute.side_effect = [
        _query_result(first=brand),
        _query_result(all_rows=[variant]),
        _query_result(scalar=1200),
    ]
    provider = AsyncMock()
    provider.parse_intent.return_value = ExtensionIntent(
        category="kurta", color="blue", size="M", priceMax=5000, audience="men"
    )
    search_result = SearchResult(
        products=[product],
        total=1,
        effective_occasion=None,
        effective_category="kurta",
        dropped_occasion=False,
        dropped_category=False,
    )
    service = ExtensionSearchService(session, None, provider)

    mocked_search = AsyncMock(return_value=search_result)
    with patch("resham.extension.service.run_search", new=mocked_search) as run:
        response = await service.search(
            "blue kurta size M under 5000",
            "https://www.outfitters.com.pk",
        )

    filters = run.call_args.args[2]
    assert filters.brands == ["outfitters"]
    assert filters.category == "kurta"
    assert filters.color == "blue"
    assert filters.size == "M"
    assert response.products[0].id == "outfitters:42"
    assert response.products[0].image_url == "https://cdn.example/blue.jpg"
    assert response.products[0].match_details.image_matches_color is True
    # Real Shopify variant id, for the popup's cart/add.js hand-off — not
    # the catalog's internal composite key.
    assert [v.model_dump() for v in response.products[0].variants] == [
        {"variant_id": "v1", "color": "Blue", "size": "M", "available": True}
    ]
    assert response.meta.store_domain == "outfitters.com.pk"
    assert response.meta.fetched_count == 1200
    assert response.meta.catalog_capped is False


@pytest.mark.asyncio
async def test_unknown_store_is_rejected_before_intent_provider_call():
    session = AsyncMock()
    session.execute.return_value = _query_result(first=None)
    provider = AsyncMock()
    service = ExtensionSearchService(session, None, provider)

    with pytest.raises(ExtensionSearchError) as caught:
        await service.search("shirt", "https://evil.example")

    assert caught.value.code == "UNSUPPORTED_STORE"
    provider.parse_intent.assert_not_awaited()


@pytest.mark.parametrize(
    "origin",
    ["http://outfitters.com.pk", "https://user@outfitters.com.pk", "not a url"],
)
@pytest.mark.asyncio
async def test_unsafe_store_origins_are_rejected(origin):
    service = ExtensionSearchService(AsyncMock(), None, AsyncMock())

    with pytest.raises(ExtensionSearchError) as caught:
        await service.search("shirt", origin)

    assert caught.value.code == "UNSUPPORTED_STORE"
