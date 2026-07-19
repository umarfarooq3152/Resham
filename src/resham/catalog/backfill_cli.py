"""One-off re-enrichment of existing product rows from already-stored text —
no Shopify network calls.

`upsert_brand_products` (catalog/repository.py) already re-derives every
classification field on each successful crawl, but a crawl can be blocked
for an extended period (rate limiting, a broken storefront) while a NLP
heuristic in this codebase still improves — this script re-runs that same
derivation against rows already in Postgres so an improvement reaches the
catalog immediately instead of waiting on the next successful crawl.

Usage: `python -m resham.catalog.backfill_cli [--batch-size 500]`
"""

import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from resham.catalog.mapper import is_kids_apparel, product_department
from resham.catalog.product_view import row_to_pydantic_product
from resham.db.connection import close_db, get_session_maker, init_db
from resham.db.models.brand import Brand
from resham.db.models.product import Product as ProductRow
from resham.nlp.keyword_matcher import tag_product
from resham.nlp.kids_age import extract_age_ranges

logger = logging.getLogger(__name__)


def _reenrich_row(row: ProductRow, brand_department: str) -> bool:
    """Recompute every derived field on `row` in place. Returns True if
    anything actually changed, so the caller can reset embedded_at only
    when a re-embed is actually needed."""
    product = row_to_pydantic_product(row)
    tag_product(product)
    semantics = product.semantics

    is_kids = is_kids_apparel(
        row.title, row.category, row.shopify_tags, row.vendor, row.description_text
    )
    # Never overwrite a department a real crawl already set — this is a
    # fallback for rows that predate that fallback existing, not a
    # downgrade path.
    department = row.department or (
        product_department(row.title, row.category, row.shopify_tags, row.vendor)
        or brand_department
    )
    age_ranges = (
        extract_age_ranges(
            [*row.sizes, *row.shopify_tags, row.title, row.category or "", row.vendor or ""]
        )
        if is_kids
        else []
    )

    new_values = {
        "tags": product.tags,
        "occasion": product.occasion,
        "product_family": semantics.product_family if semantics else None,
        "text_derived_color": semantics.text_derived_color if semantics else None,
        "product_tradition": semantics.product_tradition if semantics else None,
        "product_formality": semantics.product_formality if semantics else None,
        "is_kids": is_kids,
        "department": department,
        "age_ranges_months": [list(r) for r in age_ranges],
    }
    changed = any(getattr(row, field) != value for field, value in new_values.items())
    for field, value in new_values.items():
        setattr(row, field, value)
    if changed:
        row.embedded_at = None
    return changed


async def run_backfill(session_maker: async_sessionmaker, *, batch_size: int) -> dict[str, int]:
    async with session_maker() as session:
        brands = {b.id: b.department for b in (await session.execute(select(Brand))).scalars()}

    total = 0
    changed_count = 0
    last_id = None

    while True:
        async with session_maker() as session:
            query = select(ProductRow).order_by(ProductRow.id).limit(batch_size)
            if last_id is not None:
                query = query.where(ProductRow.id > last_id)
            rows = list((await session.execute(query)).scalars().all())
            if not rows:
                break

            for row in rows:
                if _reenrich_row(row, brands.get(row.brand_id, "unisex")):
                    changed_count += 1

            await session.commit()
            last_id = rows[-1].id
            total += len(rows)
            logger.info("Backfilled %d rows so far (%d changed)", total, changed_count)

    return {"total": total, "changed": changed_count}


async def _run(batch_size: int) -> None:
    await init_db()
    try:
        stats = await run_backfill(get_session_maker(), batch_size=batch_size)
        print(f"Backfill complete: {stats}")
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-enrich existing product rows from stored text (no network)."
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_run(args.batch_size))


if __name__ == "__main__":
    main()
