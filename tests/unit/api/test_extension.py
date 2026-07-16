from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from resham.api.routers.extension import search_store
from resham.extension.service import ExtensionSearchError
from resham.schemas.extension import (
    ExtensionIntent,
    ExtensionSearchMeta,
    ExtensionSearchRequest,
    ExtensionSearchResponse,
)


@pytest.mark.asyncio
async def test_extension_route_preserves_camel_case_contract():
    service = AsyncMock()
    service.search.return_value = ExtensionSearchResponse(
        intent=ExtensionIntent(category="t-shirt", priceMax=3000),
        products=[],
        meta=ExtensionSearchMeta(
            storeDomain="outfitters.com.pk",
            fetchedCount=500,
            catalogCapped=False,
            durationMs=12,
        ),
    )
    payload = ExtensionSearchRequest(
        query="t-shirt under 3000", storeOrigin="https://outfitters.com.pk"
    )

    result = await search_store.__wrapped__(MagicMock(), payload, service)
    body = result.model_dump(by_alias=True)

    assert body["intent"]["priceMax"] == 3000
    assert body["meta"]["storeDomain"] == "outfitters.com.pk"
    assert body["meta"]["catalogCapped"] is False
    service.search.assert_awaited_once_with(payload.query, payload.store_origin, None)


@pytest.mark.asyncio
async def test_extension_route_returns_typed_store_error():
    service = AsyncMock()
    service.search.side_effect = ExtensionSearchError(
        "UNSUPPORTED_STORE", "This store is not in Resham's crawled catalog yet."
    )
    payload = ExtensionSearchRequest(query="shirt", storeOrigin="https://evil.example")

    with pytest.raises(HTTPException) as caught:
        await search_store.__wrapped__(MagicMock(), payload, service)

    assert caught.value.status_code == 400
    assert caught.value.detail["code"] == "UNSUPPORTED_STORE"
