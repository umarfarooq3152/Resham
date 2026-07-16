"""Recurring crawl/index worker process.

Runs the durable catalog crawl and incremental Chroma sync outside the API
process so scheduled background work cannot interfere with request handling.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
from collections.abc import Sequence
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from resham.config import Settings, get_settings
from resham.crawler.orchestrator import crawl_all
from resham.db.connection import close_db, get_session_maker, init_db
from resham.vectorstore.client import get_collection
from resham.vectorstore.indexer import index_incremental

logger = logging.getLogger(__name__)


async def run_cycle(*, trigger: str, brand_slugs: list[str] | None = None) -> dict[str, Any]:
    """Run one full crawl followed by incremental vector indexing."""
    session_maker = get_session_maker()
    crawl_run_id = await crawl_all(session_maker, trigger=trigger, brand_slugs=brand_slugs)

    async with session_maker() as session:
        index_stats = await index_incremental(session, get_collection())

    result = {
        "crawl_run_id": str(crawl_run_id),
        "trigger": trigger,
        "brands": brand_slugs or [],
        "indexing": index_stats,
    }
    logger.info("Worker cycle complete: %s", result)
    return result


async def scheduled_cycle() -> None:
    """Scheduler job wrapper with error logging."""
    try:
        await run_cycle(trigger="scheduled")
    except Exception:
        logger.exception("Scheduled crawl/index cycle failed")


def schedule_worker_jobs(scheduler: AsyncIOScheduler, settings: Settings) -> None:
    """Register the recurring crawl/index job on the provided scheduler."""
    interval_seconds = max(1, math.ceil(settings.crawl_interval_hours * 3600))
    scheduler.add_job(
        scheduled_cycle,
        "interval",
        seconds=interval_seconds,
        id="crawl_and_index",
        name="Crawl catalogs and sync vectors",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=max(60, interval_seconds),
    )


async def run_worker_forever(*, run_on_startup: bool = True) -> None:
    """Start the recurring scheduler and keep the worker alive."""
    settings = get_settings()
    scheduler = AsyncIOScheduler()

    await init_db()
    try:
        schedule_worker_jobs(scheduler, settings)
        scheduler.start()
        logger.info(
            "Worker scheduler started: interval_hours=%s",
            settings.crawl_interval_hours,
        )

        if run_on_startup:
            await scheduled_cycle()

        await asyncio.Event().wait()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Worker scheduler stopped")
        await close_db()


async def run_once(brand_slugs: list[str] | None = None) -> dict[str, Any]:
    """Run one crawl/index cycle and exit."""
    await init_db()
    try:
        return await run_cycle(trigger="manual", brand_slugs=brand_slugs)
    finally:
        await close_db()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Resham crawl/index worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single crawl/index cycle and exit.",
    )
    parser.add_argument(
        "--brand",
        action="append",
        dest="brand_slugs",
        help="Limit a one-off run to this brand slug (repeatable).",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help=(
            "When running continuously, wait until the first scheduled interval "
            "before crawling."
        ),
    )
    args = parser.parse_args(argv)
    if args.brand_slugs and not args.once:
        parser.error("--brand is only valid with --once.")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.once:
        result = asyncio.run(run_once(args.brand_slugs))
        print(json.dumps(result))
        return

    try:
        asyncio.run(run_worker_forever(run_on_startup=not args.skip_initial_run))
    except KeyboardInterrupt:
        logger.info("Worker interrupted, exiting")


if __name__ == "__main__":
    main()
