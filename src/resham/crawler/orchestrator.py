"""Crawl orchestration across all active brands.

Iterates brands with bounded concurrency, isolating each brand in its own
try/except and its own DB transaction so one broken storefront never blocks
or rolls back the other 24 — the reliability property this whole project
exists for.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from resham.catalog.mapper import map_shopify_batch
from resham.catalog.repository import upsert_brand_products
from resham.catalog.shopify_client import ShopifyClient
from resham.config import get_settings
from resham.db.models.brand import Brand
from resham.db.models.crawl_run import CrawlRun, CrawlRunBrand

logger = logging.getLogger(__name__)


async def _crawl_one_brand(
    session_maker: async_sessionmaker,
    crawl_run_id: UUID,
    brand: Brand,
    client: ShopifyClient,
) -> CrawlRunBrand:
    settings = get_settings()
    started_at = datetime.now(timezone.utc)
    start = time.monotonic()

    run_brand = CrawlRunBrand(
        crawl_run_id=crawl_run_id,
        brand_id=brand.id,
        status="running",
        started_at=started_at,
    )

    try:
        raw_products = await client.fetch_all_products(
            brand.domain,
            max_pages=settings.shopify_max_pages_per_brand,
        )
        mapped = map_shopify_batch(raw_products, brand.domain)

        async with session_maker() as session:
            stats = await upsert_brand_products(session, brand.id, brand.slug, mapped)
            await session.commit()

        run_brand.status = "success"
        run_brand.products_fetched = len(raw_products)
        run_brand.products_mapped = stats.mapped
        run_brand.products_upserted = stats.upserted
        run_brand.products_unchanged = stats.unchanged
        run_brand.products_removed = stats.removed
        logger.info(
            "Crawled %s: fetched=%d mapped=%d upserted=%d unchanged=%d removed=%d",
            brand.slug, len(raw_products), stats.mapped, stats.upserted,
            stats.unchanged, stats.removed,
        )
    except Exception as exc:
        logger.exception("Crawl failed for brand %s", brand.slug)
        run_brand.status = "failed"
        run_brand.error_message = str(exc)[:2000]

    run_brand.duration_ms = int((time.monotonic() - start) * 1000)
    run_brand.finished_at = datetime.now(timezone.utc)
    return run_brand


async def crawl_all(
    session_maker: async_sessionmaker,
    *,
    trigger: str = "manual",
    brand_slugs: list[str] | None = None,
) -> UUID:
    """Crawl all active, crawl-enabled brands (or a specific subset by slug).

    Returns the crawl_run id so callers can inspect its rolled-up stats.
    """
    settings = get_settings()

    async with session_maker() as session:
        query = select(Brand).where(Brand.is_active.is_(True), Brand.crawl_enabled.is_(True))
        if brand_slugs:
            query = query.where(Brand.slug.in_(brand_slugs))
        brands = list((await session.execute(query)).scalars().all())

        run = CrawlRun(status="running", trigger=trigger)
        session.add(run)
        await session.flush()
        crawl_run_id = run.id
        await session.commit()

    client = ShopifyClient(timeout=int(settings.shopify_request_timeout_seconds))
    semaphore = asyncio.Semaphore(settings.crawl_concurrency)

    async def _bounded(brand: Brand) -> CrawlRunBrand:
        async with semaphore:
            return await _crawl_one_brand(session_maker, crawl_run_id, brand, client)

    results = await asyncio.gather(*(_bounded(brand) for brand in brands))

    async with session_maker() as session:
        for run_brand in results:
            session.add(run_brand)

        succeeded = sum(1 for r in results if r.status == "success")
        failed = sum(1 for r in results if r.status == "failed")
        overall_status = "success" if failed == 0 else ("failed" if succeeded == 0 else "partial_failure")

        run = await session.get(CrawlRun, crawl_run_id)
        run.status = overall_status
        run.finished_at = datetime.now(timezone.utc)
        run.stats = {
            "brands_total": len(brands),
            "brands_succeeded": succeeded,
            "brands_failed": failed,
            "products_upserted": sum(r.products_upserted for r in results),
            "products_unchanged": sum(r.products_unchanged for r in results),
            "products_removed": sum(r.products_removed for r in results),
        }
        await session.commit()

    logger.info("Crawl run %s finished: %s", crawl_run_id, overall_status)
    return crawl_run_id
