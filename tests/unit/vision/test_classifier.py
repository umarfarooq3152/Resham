from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from resham.vision.classifier import VisionClassification, classify_product_image


def _mock_image_response():
    response = Mock()
    response.raise_for_status = Mock()
    response.content = b"fake-bytes"
    response.headers = {"content-type": "image/jpeg"}
    return response


@pytest.mark.asyncio
async def test_classify_product_image_returns_parsed_result_on_success():
    genai_response = Mock()
    genai_response.parsed = VisionClassification(category="kurta", colors=["red", "gold"])

    with (
        patch("resham.vision.classifier.httpx.AsyncClient") as mock_client_cls,
        patch("resham.vision.classifier.genai.Client") as mock_genai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_image_response())
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_genai_client = Mock()
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=genai_response)
        mock_genai_cls.return_value = mock_genai_client

        result = await classify_product_image(
            "https://example.com/a.jpg", api_key="k", model="m", timeout_seconds=5.0,
        )

    assert result == VisionClassification(category="kurta", colors=["red", "gold"])


@pytest.mark.asyncio
async def test_classify_product_image_falls_back_to_parsing_response_text():
    genai_response = Mock()
    genai_response.parsed = None
    genai_response.text = '{"category": "abaya", "colors": ["black"]}'

    with (
        patch("resham.vision.classifier.httpx.AsyncClient") as mock_client_cls,
        patch("resham.vision.classifier.genai.Client") as mock_genai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_image_response())
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_genai_client = Mock()
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=genai_response)
        mock_genai_cls.return_value = mock_genai_client

        result = await classify_product_image(
            "https://example.com/a.jpg", api_key="k", model="m", timeout_seconds=5.0,
        )

    assert result == VisionClassification(category="abaya", colors=["black"])


@pytest.mark.asyncio
async def test_classify_product_image_returns_none_when_image_download_fails():
    with patch("resham.vision.classifier.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await classify_product_image(
            "https://example.com/a.jpg", api_key="k", model="m", timeout_seconds=5.0,
        )

    assert result is None


@pytest.mark.asyncio
async def test_classify_product_image_returns_none_when_gemini_call_fails():
    with (
        patch("resham.vision.classifier.httpx.AsyncClient") as mock_client_cls,
        patch("resham.vision.classifier.genai.Client") as mock_genai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_image_response())
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_genai_client = Mock()
        mock_genai_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("quota"))
        mock_genai_cls.return_value = mock_genai_client

        result = await classify_product_image(
            "https://example.com/a.jpg", api_key="k", model="m", timeout_seconds=5.0,
        )

    assert result is None


@pytest.mark.asyncio
async def test_classify_product_image_returns_none_on_unparseable_response():
    genai_response = Mock()
    genai_response.parsed = None
    genai_response.text = "not json"

    with (
        patch("resham.vision.classifier.httpx.AsyncClient") as mock_client_cls,
        patch("resham.vision.classifier.genai.Client") as mock_genai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_image_response())
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_genai_client = Mock()
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=genai_response)
        mock_genai_cls.return_value = mock_genai_client

        result = await classify_product_image(
            "https://example.com/a.jpg", api_key="k", model="m", timeout_seconds=5.0,
        )

    assert result is None
