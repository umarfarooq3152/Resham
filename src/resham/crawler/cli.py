"""Manual crawl entrypoint: `python -m resham.crawler.cli --once [--brand slug ...]`

Independent of the scheduler — useful for verification and ad hoc re-crawls.
"""

import argparse
import asyncio
import logging

from resham.crawler.orchestrator import crawl_all
from resham.db.connection import close_db, get_session_maker, init_db


async def _run(brand_slugs: list[str] | None) -> None:
    await init_db()
    try:
        session_maker = get_session_maker()
        crawl_run_id = await crawl_all(session_maker, trigger="manual", brand_slugs=brand_slugs)
        print(f"Crawl run complete: {crawl_run_id}")
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a one-off catalog crawl.")
    parser.add_argument("--once", action="store_true", help="Run a single crawl cycle and exit.")
    parser.add_argument(
        "--brand",
        action="append",
        dest="brand_slugs",
        help="Limit the crawl to this brand slug (repeatable). Omit to crawl all active brands.",
    )
    args = parser.parse_args()

    if not args.once:
        parser.error("Only --once is currently supported; the recurring schedule runs via resham.worker.main")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_run(args.brand_slugs))


if __name__ == "__main__":
    main()
