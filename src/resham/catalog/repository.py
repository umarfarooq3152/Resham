"""Postgres upsert/dedup for crawled products — the durable source of truth
that replaces Dhaaga's request-time live fetch.

Natural key is (brand_id, external_id). On each crawl: recompute the
content hash from the mapped record's text fields — unchanged means only
bump `last_seen_at` (no re-embed triggered); changed means update the row
and reset `embedded_at` so the vectorstore indexer picks it up. Products
missing from a crawl are aged out via `catalog.freshness`, never deleted.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.catalog.content_hash import compute_content_hash
from resham.catalog.freshness import on_product_missing, on_product_seen
from resham.catalog.mapper import MappedProduct
from resham.config import get_settings
from resham.db.models.brand import Brand
from resham.db.models.product import Product as ProductRow
from resham.db.models.product_variant import ProductVariant as VariantRow
from resham.nlp.keyword_matcher import tag_product
from resham.schemas.product import Product as PydanticProduct

logger = logging.getLogger(__name__)


@dataclass
class UpsertStats:
    mapped: int = 0
    upserted: int = 0
    unchanged: int = 0
    removed: int = 0


def _mapped_to_pydantic(mapped: MappedProduct, brand_slug: str) -> PydanticProduct:
    """Bridge to the API-facing Product schema so the existing NLP tagging
    pipeline (occasion/tags/product_family via keyword_matcher +
    product_semantics) runs unmodified against crawled data."""
    return PydanticProduct(
        id=f"{brand_slug}:{mapped.external_id}",
        name=mapped.title,
        description=mapped.description_text,
        price=mapped.min_price,
        colors=mapped.colors,
        color_images=mapped.color_images,
        sizes=mapped.sizes,
        occasion=None,
        category=mapped.category,
        tags=[],
        shopify_tags=mapped.shopify_tags,
        is_kids=mapped.is_kids,
        department=mapped.department,
        age_ranges_months=[tuple(r) for r in mapped.age_ranges_months],
        image=mapped.primary_image_url,
        secondaryImage=mapped.secondary_image_url,
        product_url=mapped.product_url,
    )


async def _upsert_variants(session: AsyncSession, product_row: ProductRow, mapped: MappedProduct) -> None:
    """Query variants directly by product_id rather than through the ORM
    relationship — `product_row.variants` would trigger an implicit lazy
    load on a freshly-flushed instance, which async SQLAlchemy disallows
    outside a greenlet context."""
    existing_result = await session.execute(
        select(VariantRow).where(VariantRow.product_id == product_row.id)
    )
    existing = {v.external_variant_id: v for v in existing_result.scalars().all()}
    seen_ids: set[str] = set()

    for variant in mapped.variants:
        seen_ids.add(variant.external_variant_id)
        row = existing.get(variant.external_variant_id)
        if row is None:
            row = VariantRow(product_id=product_row.id, external_variant_id=variant.external_variant_id)
            session.add(row)
        row.color = variant.color
        row.size = variant.size
        row.extra_options = variant.extra_options
        row.price = variant.price
        row.compare_at_price = variant.compare_at_price
        row.available = variant.available
        row.image_url = variant.image_url
        row.sku = variant.sku

    # A variant no longer present in the latest fetch has been discontinued.
    for external_variant_id, row in existing.items():
        if external_variant_id not in seen_ids:
            await session.delete(row)


async def upsert_brand_products(
    session: AsyncSession,
    brand_id: UUID,
    brand_slug: str,
    mapped_products: list[MappedProduct],
) -> UpsertStats:
    """Upsert one brand's freshly crawled+mapped products, and age out any
    previously-known products for this brand absent from this crawl."""
    settings = get_settings()
    stats = UpsertStats(mapped=len(mapped_products))

    # Ground truth, curated per-brand (seed/brands.json), for the ~38% of
    # products where the title/category/tags alone name no gender word at
    # all — a single-gender brand's product IS that gender, not a guess,
    # and this was previously hard-excluding those products from every
    # department-filtered search.
    brand = await session.get(Brand, brand_id)
    brand_department = brand.department if brand else "unisex"

    existing_rows_result = await session.execute(
        select(ProductRow).where(ProductRow.brand_id == brand_id)
    )
    existing_by_external_id = {row.external_id: row for row in existing_rows_result.scalars().all()}

    seen_external_ids: set[str] = set()

    for mapped in mapped_products:
        seen_external_ids.add(mapped.external_id)

        pydantic_product = _mapped_to_pydantic(mapped, brand_slug)
        tagged = tag_product(pydantic_product)
        occasion = tagged.occasion or None
        tags = tagged.tags
        product_family = tagged.semantics.product_family if tagged.semantics else None
        text_derived_color = tagged.semantics.text_derived_color if tagged.semantics else None
        product_tradition = tagged.semantics.product_tradition if tagged.semantics else None
        product_formality = tagged.semantics.product_formality if tagged.semantics else None

        content_hash = compute_content_hash(mapped, occasion, tags)

        row = existing_by_external_id.get(mapped.external_id)
        is_new = row is None
        if is_new:
            row = ProductRow(
                brand_id=brand_id,
                external_id=mapped.external_id,
                composite_key=f"{brand_slug}:{mapped.external_id}",
            )
            session.add(row)

        changed = is_new or row.content_hash != content_hash
        freshness = on_product_seen()

        row.handle = mapped.handle
        row.title = mapped.title
        row.description_html = mapped.description_html
        row.description_text = mapped.description_text
        row.category = mapped.category
        row.product_family = product_family
        row.text_derived_color = text_derived_color
        row.product_tradition = product_tradition
        row.product_formality = product_formality
        row.vendor = mapped.vendor
        row.shopify_tags = mapped.shopify_tags
        row.tags = tags
        row.department = mapped.department or brand_department
        row.is_kids = mapped.is_kids
        row.age_ranges_months = [list(r) for r in mapped.age_ranges_months]
        row.occasion = occasion
        row.colors = mapped.colors
        row.sizes = mapped.sizes
        row.color_images = mapped.color_images
        row.min_price = mapped.min_price
        row.max_price = mapped.max_price
        row.currency = mapped.currency
        row.primary_image_url = mapped.primary_image_url
        row.secondary_image_url = mapped.secondary_image_url
        row.product_url = mapped.product_url
        row.in_stock = mapped.in_stock
        row.raw_shopify_json = mapped.raw_shopify_json
        row.missing_streak = freshness.missing_streak
        if freshness.should_clear_removed_at:
            row.removed_at = None

        if changed:
            row.content_hash = content_hash
            row.embedded_at = None  # marks it for re-embedding
            stats.upserted += 1
        else:
            stats.unchanged += 1

        await session.flush()  # assign row.id before touching variants
        await _upsert_variants(session, row, mapped)

    for external_id, row in existing_by_external_id.items():
        if external_id in seen_external_ids:
            continue
        freshness = on_product_missing(row.missing_streak, settings.crawl_missing_grace_cycles)
        row.missing_streak = freshness.missing_streak
        if freshness.in_stock is not None:
            row.in_stock = freshness.in_stock
            stats.removed += 1
        if freshness.removed_at is not None:
            row.removed_at = freshness.removed_at

    await session.flush()
    return stats
