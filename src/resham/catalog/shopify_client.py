"""Shopify API client for fetching products from brand storefronts.

Ported from Dhaaga's app/shopify/client.py — this is a pure HTTP fetch
building block, invoked here on a schedule by the crawler rather than live
at request time.
"""

import asyncio
import logging
import random
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# aiohttp's default User-Agent ("Python/3.x aiohttp/3.x") is blocked with a 429
# by Shopify/Cloudflare's bot protection on every storefront tested — curl and
# a real browser UA succeed against the identical URL. A browser-like UA is
# required for /products.json to return data at all.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class ShopifyFetchError(Exception):
    """A page request failed (rate limit, 5xx, timeout, network error) —
    distinct from a confirmed HTTP 200 empty response. Raised instead of
    returned so _crawl_one_brand's existing try/except marks the whole
    brand crawl "failed" and skips upsert_brand_products entirely, rather
    than the caller treating an empty result as "this brand now has zero
    products" and running freshness/missing logic against every existing
    row for that brand."""


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After is nearly always a plain integer seconds count from
    Shopify/Cloudflare; the HTTP-date form is technically legal but never
    observed in practice, so it's treated as absent rather than parsed."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class ShopifyClient:
    """Async HTTP client for Shopify's public products JSON endpoint."""

    def __init__(
        self,
        timeout: int = 30,
        *,
        max_retries: int = 3,
        retry_base_seconds: float = 2.0,
        retry_max_seconds: float = 30.0,
        sleep_fn=asyncio.sleep,
    ):
        """Initialize Shopify client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Retries per page fetch on 429/5xx/timeout/network
                error before giving up on this brand for the current cycle.
            retry_base_seconds: Exponential backoff base when the server
                gives no Retry-After header.
            retry_max_seconds: Cap on any single wait, whether computed via
                backoff or read from a (misbehaving, very long) Retry-After.
            sleep_fn: Injectable for tests — real callers always use the
                default asyncio.sleep.
        """
        self.timeout = timeout
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._sleep = sleep_fn
        # One session per client (one per crawl run, see orchestrator.py) —
        # reused across every brand/page instead of a fresh TCP+TLS
        # handshake per request, both cheaper and closer to how a real
        # browser tab's connection behaves.
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "ShopifyClient":
        self._session = aiohttp.ClientSession(headers={"User-Agent": BROWSER_USER_AGENT})
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("ShopifyClient must be used as an async context manager")
        return self._session

    async def fetch_products(
        self, domain: str, limit: int = 250, page: int = 1
    ) -> dict[str, Any]:
        """Fetch one page of products from a Shopify storefront, retrying
        on a rate limit, transient server error, timeout, or network error.

        Returns:
            Response dict with a products list

        Raises:
            ShopifyFetchError: Every retry attempt was exhausted.
        """
        url = f"https://{domain}/products.json"
        params = {"limit": min(max(limit, 1), 250), "page": max(page, 1)}
        session = self._require_session()

        attempt = 0
        while True:
            try:
                async with session.get(url, params=params, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 404:
                        logger.warning(f"Shopify endpoint not found for {domain}")
                        return {"products": []}
                    if resp.status in _RETRYABLE_STATUSES and attempt < self._max_retries:
                        wait = self._backoff_seconds(attempt, _parse_retry_after(resp.headers.get("Retry-After")))
                        logger.warning(
                            "Shopify API status=%d for %s (attempt %d/%d), retrying in %.1fs",
                            resp.status, domain, attempt + 1, self._max_retries, wait,
                        )
                        await self._sleep(wait)
                        attempt += 1
                        continue
                    logger.error(f"Shopify API error for {domain}: status={resp.status}")
                    raise ShopifyFetchError(f"{domain} returned status={resp.status}")
            except asyncio.TimeoutError as e:
                if attempt < self._max_retries:
                    wait = self._backoff_seconds(attempt, None)
                    logger.warning(
                        "Timeout fetching from %s (attempt %d/%d), retrying in %.1fs",
                        domain, attempt + 1, self._max_retries, wait,
                    )
                    await self._sleep(wait)
                    attempt += 1
                    continue
                logger.error(f"Timeout fetching products from {domain}")
                raise ShopifyFetchError(f"Timeout fetching from {domain}") from e
            except aiohttp.ClientError as e:
                if attempt < self._max_retries:
                    wait = self._backoff_seconds(attempt, None)
                    logger.warning(
                        "Failed to fetch from %s (attempt %d/%d): %s, retrying in %.1fs",
                        domain, attempt + 1, self._max_retries, e, wait,
                    )
                    await self._sleep(wait)
                    attempt += 1
                    continue
                logger.error(f"Failed to fetch from {domain}: {e}")
                raise ShopifyFetchError(f"Failed to fetch from {domain}: {e}") from e

    def _backoff_seconds(self, attempt: int, retry_after: float | None) -> float:
        """Retry-After (server-specified) wins when present; otherwise
        exponential backoff with jitter, since a uniform/deterministic
        delay pattern is itself a bot signal. Either way, capped so a
        misbehaving header can't stall a whole crawl cycle."""
        if retry_after is not None:
            return min(retry_after, self._retry_max_seconds)
        base = self._retry_base_seconds * (2**attempt)
        jittered = base * random.uniform(1.0, 1.5)
        return min(jittered, self._retry_max_seconds)

    async def fetch_all_products(
        self, domain: str, max_pages: int = 20, max_products: int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all products from a brand, handling pagination.

        Args:
            domain: Brand domain (e.g., 'limelight.pk')
            max_pages: Max number of pages to fetch (safety limit)

        Returns:
            List of all product objects
        """
        all_products = []
        page_count = 0
        seen_ids: set[str] = set()
        page_size = 250

        while page_count < max_pages:
            response = await self.fetch_products(
                domain, limit=page_size, page=page_count + 1
            )
            products = response.get("products", [])

            if not isinstance(products, list) or not products:
                break

            new_products = []
            for product in products:
                product_id = str(product.get("id", "")) if isinstance(product, dict) else ""
                if not product_id or product_id in seen_ids:
                    continue
                seen_ids.add(product_id)
                new_products.append(product)

            # A storefront returning the same page repeatedly must not create
            # an unbounded loop or duplicate catalog entries.
            if not new_products:
                break

            all_products.extend(new_products)
            page_count += 1

            if max_products is not None and len(all_products) >= max_products:
                all_products = all_products[:max_products]
                break

            if len(products) < page_size:
                break

            logger.debug(
                f"Fetched page {page_count} from {domain}: "
                f"{len(new_products)} new products, "
                f"total: {len(all_products)}"
            )

        logger.info(
            f"Fetched {len(all_products)} total products from {domain} "
            f"in {page_count} pages"
        )
        return all_products
