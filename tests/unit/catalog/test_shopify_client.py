"""Tests for ShopifyClient's retry/backoff behavior — the fix for a real
incident where a single crawl cycle got 24 of 25 brands rate limited
(HTTP 429) with zero retries and zero backoff, immediately failing each
brand outright."""

from unittest.mock import MagicMock

import pytest

from resham.catalog.shopify_client import ShopifyClient, ShopifyFetchError


class _FakeResponse:
    def __init__(self, status, json_body=None, headers=None):
        self.status = status
        self._json_body = json_body if json_body is not None else {}
        self.headers = headers or {}

    async def json(self):
        return self._json_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _fake_session(*responses):
    """A fake aiohttp session whose .get() yields each response in sequence."""
    session = MagicMock()
    iterator = iter(responses)
    session.get = MagicMock(side_effect=lambda *a, **kw: next(iterator))
    return session


def _client(*, max_retries=3, retry_base_seconds=2.0, retry_max_seconds=30.0):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = ShopifyClient(
        max_retries=max_retries,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
        sleep_fn=fake_sleep,
    )
    return client, sleeps


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    client, sleeps = _client(max_retries=3)
    client._session = _fake_session(
        _FakeResponse(429, headers={"Retry-After": "5"}),
        _FakeResponse(200, json_body={"products": [{"id": 1}]}),
    )

    result = await client.fetch_products("example.com")

    assert result == {"products": [{"id": 1}]}
    assert sleeps == [5.0]  # honored Retry-After exactly, no backoff guess


@pytest.mark.asyncio
async def test_exhausts_retries_and_raises():
    client, _ = _client(max_retries=2)
    client._session = _fake_session(
        _FakeResponse(429), _FakeResponse(429), _FakeResponse(429),
    )

    with pytest.raises(ShopifyFetchError):
        await client.fetch_products("example.com")


@pytest.mark.asyncio
async def test_404_returns_empty_without_retry_or_sleep():
    client, sleeps = _client(max_retries=3)
    client._session = _fake_session(_FakeResponse(404))

    result = await client.fetch_products("example.com")

    assert result == {"products": []}
    assert sleeps == []


@pytest.mark.asyncio
async def test_backoff_without_retry_after_grows_exponentially_with_jitter():
    client, sleeps = _client(max_retries=3, retry_base_seconds=2.0, retry_max_seconds=30.0)
    client._session = _fake_session(
        _FakeResponse(503), _FakeResponse(503), _FakeResponse(200, json_body={"products": []}),
    )

    await client.fetch_products("example.com")

    assert len(sleeps) == 2
    assert 2.0 <= sleeps[0] <= 3.0  # base=2 * 2**0 * [1.0, 1.5]
    assert 4.0 <= sleeps[1] <= 6.0  # base=2 * 2**1 * [1.0, 1.5]


@pytest.mark.asyncio
async def test_backoff_is_capped_at_retry_max_seconds_even_for_a_huge_retry_after():
    client, sleeps = _client(max_retries=1, retry_max_seconds=10.0)
    client._session = _fake_session(
        _FakeResponse(429, headers={"Retry-After": "9999"}),
        _FakeResponse(200, json_body={"products": []}),
    )

    await client.fetch_products("example.com")

    assert sleeps == [10.0]


@pytest.mark.asyncio
async def test_5xx_and_timeout_are_retried_but_a_definitive_error_is_not():
    """400/401/403 etc. are not in the retryable set — a client error won't
    resolve itself on retry, unlike a rate limit or a transient 5xx."""
    client, sleeps = _client(max_retries=3)
    client._session = _fake_session(_FakeResponse(403))

    with pytest.raises(ShopifyFetchError):
        await client.fetch_products("example.com")

    assert sleeps == []


@pytest.mark.asyncio
async def test_session_lifecycle_via_async_context_manager():
    client = ShopifyClient()

    async with client as ctx:
        assert ctx is client
        assert client._session is not None
        assert not client._session.closed

    assert client._session is None
