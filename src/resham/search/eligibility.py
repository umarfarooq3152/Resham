"""The eligibility gate: hard structured filters over Postgres.

This is the correctness spine of the whole search — every product that
survives here satisfies every hard constraint (department, kids/age,
garment family, color, size, price, brand allow/exclude). Vector
similarity (search/ranking.py) is only ever allowed to *order* this set,
never to admit a product that doesn't belong in it.

Color/size/price are checked at the variant level: a product is only
eligible if at least one *available* variant simultaneously satisfies all
three — the same coexistence rule as Dhaaga's `_matching_variants`.
"""

import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.brand import Brand
from resham.db.models.product import Product as ProductRow
from resham.db.models.product_variant import ProductVariant as VariantRow
from resham.nlp.colors import colors_match
from resham.nlp.garments import garment_search_terms, matches_garment_text

# Keeps an IN(...) clause's bind-parameter count well under asyncpg/Postgres's
# hard 32767 limit — a broad, category-less color/size/budget search over a
# catalog this size can otherwise pass tens of thousands of product ids in a
# single query and crash outright.
_VARIANT_ID_BATCH_SIZE = 20_000

SIZE_ALIASES = {
    "EXTRASMALL": "XS",
    "XSMALL": "XS",
    "SMALL": "S",
    "MEDIUM": "M",
    "LARGE": "L",
    "EXTRALARGE": "XL",
    "XLARGE": "XL",
    "XXLARGE": "XXL",
    "2XL": "XXL",
    "XXXLARGE": "XXXL",
    "3XL": "XXXL",
}


def normalize_size(value: str) -> str:
    compact = re.sub(r"[^A-Z0-9]+", "", value.upper())
    return SIZE_ALIASES.get(compact, compact)


@dataclass
class EligibilityFilters:
    """Hard constraints derived from the current turn's SessionState —
    never relaxed (occasion is deliberately absent: it's a soft signal
    handled by search/relax.py, matching Dhaaga's one exception)."""

    department: str | None = None
    wants_kids: bool = False
    child_age_months: int | None = None
    category: str | None = None
    color: str | None = None
    size: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    brands: list[str] = field(default_factory=list)  # allow-list of brand slugs
    excluded_brands: list[str] = field(default_factory=list)


def _product_matches_age(row: ProductRow, child_age_months: int) -> bool:
    # `age_ranges_months` is already fully computed at ingestion time
    # (catalog.mapper calls nlp.kids_age.extract_age_ranges), so — unlike
    # Dhaaga's live-fetch fallback path — there is no lazy re-derivation
    # from title/sizes/tags needed here.
    return any(start <= child_age_months <= end for start, end in row.age_ranges_months)


def _normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


async def _catalog_alias_terms(session: AsyncSession, filters: EligibilityFilters) -> list[str]:
    """Learn store/category aliases from rows already mapped to this family.

    Example: if Outfitters rows with product_family="t-shirt" commonly carry
    Shopify category "TEES", then "tees" becomes a SQL prefilter term for
    future t-shirt searches. This widens only the cheap DB prefilter; the
    authoritative matches_garment_text check below still decides eligibility.
    """
    if not filters.category:
        return []

    canonical_terms = garment_search_terms(filters.category)
    stmt = select(ProductRow.category, ProductRow.shopify_tags).where(
        ProductRow.in_stock.is_(True),
        ProductRow.removed_at.is_(None),
        ProductRow.is_kids.is_(filters.wants_kids),
        or_(*(ProductRow.product_family.ilike(f"%{term}%") for term in canonical_terms)),
    )

    if filters.brands or filters.excluded_brands:
        stmt = stmt.join(Brand, Brand.id == ProductRow.brand_id)
        if filters.brands:
            stmt = stmt.where(Brand.slug.in_(filters.brands))
        if filters.excluded_brands:
            stmt = stmt.where(Brand.slug.notin_(filters.excluded_brands))

    aliases: list[str] = []
    for category, shopify_tags in (await session.execute(stmt.limit(500))).all():
        values = [category or "", *(shopify_tags or [])]
        for value in values:
            normalized = _normalize_alias(str(value))
            if not normalized:
                continue
            if any(term in normalized for term in canonical_terms):
                aliases.append(normalized)

    return list(dict.fromkeys(aliases))


async def _variant_eligible_product_ids(
    session: AsyncSession,
    product_ids: list[UUID],
    filters: EligibilityFilters,
    text_derived_colors: dict[UUID, str | None],
) -> set[UUID]:
    """Return the subset of product_ids with at least one available variant
    that simultaneously satisfies color, size, and price.

    `text_derived_colors` (product_id -> a color extracted from
    title/tags/description at ingest, see product_semantics.py) is used
    only as a fallback when a variant has no merchant-set color at all —
    ~57% of in-stock products in the live catalog fall in this bucket and
    would otherwise be unreachable by any color-filtered search regardless
    of their actual color. It never overrides a real variant color.
    """
    if not product_ids:
        return set()

    variants: list[VariantRow] = []
    for start in range(0, len(product_ids), _VARIANT_ID_BATCH_SIZE):
        batch = product_ids[start : start + _VARIANT_ID_BATCH_SIZE]
        stmt = select(VariantRow).where(
            VariantRow.product_id.in_(batch), VariantRow.available.is_(True)
        )
        variants.extend((await session.execute(stmt)).scalars().all())

    requested_size = normalize_size(filters.size) if filters.size else None
    matching_ids: set[UUID] = set()

    for variant in variants:
        if variant.product_id in matching_ids:
            continue
        if filters.budget_min is not None and float(variant.price) < filters.budget_min:
            continue
        if filters.budget_max is not None and float(variant.price) > filters.budget_max:
            continue
        if requested_size:
            variant_size = normalize_size(variant.size) if variant.size else None
            if variant_size != requested_size:
                continue
        if filters.color:
            effective_color = variant.color or text_derived_colors.get(variant.product_id)
            if not effective_color or not colors_match(filters.color, effective_color):
                continue
        matching_ids.add(variant.product_id)

    return matching_ids


async def eligible_products(
    session: AsyncSession, filters: EligibilityFilters
) -> list[ProductRow]:
    """Return every product satisfying every hard constraint. This is the
    bounded candidate set that search/ranking.py orders — it never grows
    beyond what's genuinely eligible, regardless of ranking signal."""
    stmt = select(ProductRow).where(
        ProductRow.in_stock.is_(True),
        ProductRow.removed_at.is_(None),
        ProductRow.is_kids.is_(filters.wants_kids),
    )

    if filters.department:
        stmt = stmt.where(ProductRow.department.in_([filters.department, "unisex"]))

    if filters.brands or filters.excluded_brands:
        stmt = stmt.join(Brand, Brand.id == ProductRow.brand_id)
        if filters.brands:
            stmt = stmt.where(Brand.slug.in_(filters.brands))
        if filters.excluded_brands:
            stmt = stmt.where(Brand.slug.notin_(filters.excluded_brands))

    if filters.category:
        # Pushes matches_garment_text's candidate set down into SQL so
        # Postgres — not the app — discards the vast majority of an
        # unrelated-category catalog before it's ever transferred and
        # ORM-hydrated. ILIKE is a deliberately looser superset of
        # matches_garment_text's word-boundary regex (never a stricter
        # subset), so this can only admit extra rows, never drop a real
        # match — the identical Python check below still runs on the
        # (now far smaller) result and remains the sole authority on
        # what's actually eligible.
        search_terms = [
            *garment_search_terms(filters.category),
            *await _catalog_alias_terms(session, filters),
        ]
        stmt = stmt.where(
            or_(
                *(ProductRow.product_family.ilike(f"%{term}%") for term in search_terms),
                *(ProductRow.category.ilike(f"%{term}%") for term in search_terms),
                *(ProductRow.title.ilike(f"%{term}%") for term in search_terms),
                *(ProductRow.vision_category.ilike(f"%{term}%") for term in search_terms),
            )
        )

    rows = list((await session.execute(stmt)).scalars().all())

    if filters.wants_kids and filters.child_age_months is not None:
        # Age is a hard safety/relevance constraint — never relaxed, and
        # unknown age metadata is excluded rather than guessed.
        rows = [r for r in rows if _product_matches_age(r, filters.child_age_months)]

    if filters.category:
        # vision_category (resham.vision) is appended, never substituted —
        # it only ever adds a match for a product the text fields alone
        # couldn't place, it can't cost an already-well-tagged product one.
        rows = [
            r for r in rows
            if matches_garment_text(
                f"{r.product_family or ''} {r.category or ''} {r.title} {r.vision_category or ''}",
                filters.category,
            )
        ]

    if filters.color or filters.size or filters.budget_min is not None or filters.budget_max is not None:
        text_derived_colors = {r.id: r.text_derived_color for r in rows}
        eligible_ids = await _variant_eligible_product_ids(
            session, [r.id for r in rows], filters, text_derived_colors
        )
        rows = [r for r in rows if r.id in eligible_ids]

    return rows
