from unittest.mock import AsyncMock, patch

import pytest
from resham.vision.query import VisualSearchIntent, describe_search_image


@pytest.mark.asyncio
async def test_describe_search_image_returns_the_single_structured_gemini_result():
    response = AsyncMock()
    response.parsed = VisualSearchIntent(
        query="blue embroidered kurta", category="kurta", color="blue"
    )
    with patch("resham.vision.query.genai.Client") as client_cls:
        client_cls.return_value.aio.models.generate_content = AsyncMock(return_value=response)
        result = await describe_search_image(
            b"image-bytes", mime_type="image/jpeg", api_key="key", model="model"
        )

    assert result == VisualSearchIntent(
        query="blue embroidered kurta", category="kurta", color="blue"
    )
    client_cls.return_value.aio.models.generate_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_describe_search_image_returns_none_when_gemini_fails():
    with patch("resham.vision.query.genai.Client", side_effect=RuntimeError("down")):
        assert (
            await describe_search_image(
                b"image-bytes", mime_type="image/jpeg", api_key="key", model="model"
            )
            is None
        )
