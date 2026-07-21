"""Current-store search for the browser extension.

The extension keeps its established wire contract, but catalog reads now come
from Resham's durable Postgres rows and ranking goes through the shared search
core. No request-time Shopify fetch or product cache is involved.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from chromadb.api.models.Collection import Collection
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.brand import Brand
from resham.db.models.product import Product as ProductRow
from resham.db.models.product_variant import ProductVariant
from resham.nlp.colors import colors_match
from resham.schemas.extension import (
    ExtensionIntent,
    ExtensionMatchDetails,
    ExtensionProductResult,
    ExtensionSearchMeta,
    ExtensionSearchResponse,
    ExtensionVariantOut,
)
from resham.search.eligibility import EligibilityFilters, normalize_size
from resham.search.service import search as run_search


class ExtensionIntentProvider(Protocol):
    async def parse_intent(
        self, query: str, previous_intent: ExtensionIntent | None = None
    ) -> ExtensionIntent: ...


class ExtensionSearchError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _normalize_domain(domain: str) -> str:
    return domain.lower().rstrip(".").removeprefix("www.")


def _validate_origin(store_origin: str) -> str:
    parsed = urlsplit(store_origin)
    domain = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not domain
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ExtensionSearchError(
            "UNSUPPORTED_STORE",
            "Open a supported Resham store in the active tab.",
        )
    return domain


def _split_requested_colors(color: str | None) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"\s+or\s+", color or "", flags=re.IGNORECASE)
        if value.strip()
    ]


def _variant_matches(variant: ProductVariant, intent: ExtensionIntent) -> bool:
    price = float(variant.price)
    if not variant.available:
        return False
    if intent.price_min is not None and price < intent.price_min:
        return False
    if intent.price_max is not None and price > intent.price_max:
        return False
    if intent.size and (
        not variant.size or normalize_size(variant.size) != normalize_size(intent.size)
    ):
        return False
    requested_colors = _split_requested_colors(intent.color)
    if requested_colors and (
        not variant.color
        or not any(colors_match(requested, variant.color) for requested in requested_colors)
    ):
        return False
    return True


def _reason(intent: ExtensionIntent, *, relaxed_occasion: bool) -> str:
    facts: list[str] = []
    if intent.color:
        facts.append(f"{intent.color.title().replace(' Or ', ' or ')} option")
    if intent.size:
        facts.append(f"size {intent.size.upper()}")
    if intent.price_max is not None:
        facts.append("within your budget")
    elif intent.price_min is not None:
        facts.append("above your minimum price")
    if intent.category:
        facts.append(f"matches {intent.category}")
    if intent.occasion and not relaxed_occasion:
        facts.append(f"suited to {intent.occasion}")
    if intent.audience:
        facts.append(f"from the {intent.audience}'s department")
    if intent.wants_kids:
        facts.append("from the kids' range")
    if intent.fit:
        facts.append(f"ranked for {intent.fit} styling")
    if not facts:
        return "Matches the details in your request."
    if len(facts) == 1:
        return f"{facts[0][0].upper()}{facts[0][1:]}."
    return f"{', '.join(facts[:-1]).capitalize()}, and {facts[-1]}."


def _intent_query_text(query: str, intent: ExtensionIntent) -> str:
    normalized_query = re.sub(r"[^a-z0-9']+", " ", query.lower()).strip()
    confirmation_only = re.fullmatch(
        r"(?:yes|yeah|yep|sure|ok(?:ay)?|show(?: me)?(?: them| kids)?|"
        r"kids?|kid'?s|children'?s?|boys?|girls?)",
        normalized_query,
    )
    parts = [] if confirmation_only else [query.strip()]
    for value in (intent.color, intent.category, intent.fit, intent.descriptive, intent.occasion):
        if value and value.lower() not in query.lower():
            parts.append(value)
    if intent.audience:
        parts.append(intent.audience)
    if intent.wants_kids:
        parts.append("kids")
    return " ".join(part for part in parts if part)


class ExtensionSearchService:
    def __init__(
        self,
        session: AsyncSession,
        collection: Collection | None,
        intent_provider: ExtensionIntentProvider,
        *,
        result_limit: int = 0,
    ):
        self._session = session
        self._collection = collection
        self._provider = intent_provider
        self._result_limit = max(result_limit, 0)

    async def _resolve_brand(self, domain: str) -> Brand:
        normalized = _normalize_domain(domain)
        result = await self._session.execute(
            select(Brand).where(
                Brand.is_active.is_(True),
                or_(
                    func.lower(Brand.domain) == domain,
                    func.lower(Brand.domain) == f"www.{normalized}",
                    func.lower(Brand.domain) == normalized,
                ),
            )
        )
        brand = result.scalars().first()
        if brand is None:
            raise ExtensionSearchError(
                "UNSUPPORTED_STORE",
                "This store is not in Resham's crawled catalog yet.",
            )
        return brand

    async def _catalog_count(self, brand_id: UUID) -> int:
        return int(
            (
                await self._session.execute(
                    select(func.count(ProductRow.id)).where(
                        ProductRow.brand_id == brand_id,
                        ProductRow.in_stock.is_(True),
                        ProductRow.removed_at.is_(None),
                    )
                )
            ).scalar_one()
        )

    async def _count_matches(
        self,
        filters: EligibilityFilters,
        *,
        occasion: str | None,
        query_text: str,
        semantic_query: str,
    ) -> int:
        result = await run_search(
            self._session,
            self._collection,
            filters,
            occasion=occasion,
            occasion_is_hard=False,
            query_text=query_text,
            semantic_query=semantic_query,
        )
        return len(result.products)

    async def _variants_by_product(
        self, product_ids: list[UUID]
    ) -> dict[UUID, list[ProductVariant]]:
        if not product_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    select(ProductVariant).where(
                        ProductVariant.product_id.in_(product_ids),
                        ProductVariant.available.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[UUID, list[ProductVariant]] = defaultdict(list)
        for row in rows:
            grouped[row.product_id].append(row)
        return grouped

    async def search(
        self,
        query: str,
        store_origin: str,
        previous_intent: ExtensionIntent | None = None,
    ) -> ExtensionSearchResponse:
        started = time.monotonic()
        domain = _validate_origin(store_origin)
        brand = await self._resolve_brand(domain)
        intent = await self._provider.parse_intent(query.strip(), previous_intent)
        if not intent.has_any_signal():
            raise ExtensionSearchError(
                "EMPTY_INTENT",
                (
                    "Add a product, style, occasion, color, size, or budget "
                    "so Resham knows what to find."
                ),
                422,
            )

        filters = EligibilityFilters(
            department=intent.audience,
            wants_kids=intent.wants_kids is True,
            child_age_months=intent.child_age_months,
            category=intent.category,
            color=intent.color,
            size=intent.size,
            budget_min=intent.price_min,
            budget_max=intent.price_max,
            brands=[brand.slug],
        )
        semantic_query = " ".join(
            part.strip() for part in (intent.fit or "", intent.descriptive or "") if part.strip()
        )
        if intent.category and intent.audience is None and intent.wants_kids is None:
            query_text = _intent_query_text(query, intent)
            adult_count = await self._count_matches(
                filters,
                occasion=intent.occasion,
                query_text=query_text,
                semantic_query=semantic_query,
            )
            kids_filters = EligibilityFilters(
                department=None,
                wants_kids=True,
                child_age_months=intent.child_age_months,
                category=intent.category,
                color=intent.color,
                size=intent.size,
                budget_min=intent.price_min,
                budget_max=intent.price_max,
                brands=[brand.slug],
            )
            kids_count = await self._count_matches(
                kids_filters,
                occasion=intent.occasion,
                query_text=query_text,
                semantic_query=semantic_query,
            )
            if adult_count == 0 and kids_count > 0:
                notice = (
                    f"I couldn't find {intent.color + ' ' if intent.color else ''}"
                    f"{intent.category} in the adult section, but I found "
                    f"{kids_count} in kids. Do you want to see kids options?"
                )
            else:
                notice = "Which collection should I search: men's, women's, or kids?"
            catalog_count = await self._catalog_count(brand.id)
            return ExtensionSearchResponse(
                intent=intent,
                products=[],
                notice=notice,
                meta=ExtensionSearchMeta(
                    storeDomain=_normalize_domain(brand.domain),
                    fetchedCount=catalog_count,
                    mappedCount=catalog_count,
                    exactCount=0,
                    catalogCapped=False,
                    relaxed=False,
                    relaxedFilters=[],
                    durationMs=int((time.monotonic() - started) * 1000),
                ),
            )

        result = await run_search(
            self._session,
            self._collection,
            filters,
            occasion=intent.occasion,
            occasion_is_hard=False,
            query_text=_intent_query_text(query, intent),
            semantic_query=semantic_query,
        )
        selected = result.products if self._result_limit == 0 else result.products[: self._result_limit]
        variants_by_product = await self._variants_by_product([row.id for row in selected])
        relaxed_occasion = result.dropped_occasion

        products: list[ExtensionProductResult] = []
        total = len(selected)
        for index, row in enumerate(selected):
            available = variants_by_product.get(row.id, [])
            matching = [variant for variant in available if _variant_matches(variant, intent)]
            display_variants = matching or available
            if not display_variants:
                continue
            image = next((variant.image_url for variant in matching if variant.image_url), None)
            image_matches_color = None
            if intent.color:
                image_matches_color = image is not None
            products.append(
                ExtensionProductResult(
                    id=row.composite_key,
                    title=row.title,
                    price=min(float(variant.price) for variant in display_variants),
                    currency=row.currency,
                    imageUrl=image or row.primary_image_url or "",
                    productUrl=row.product_url or "",
                    score=round(max(1.0, 10.0 - (index * 9.0 / max(total, 1))), 1),
                    reason=_reason(intent, relaxed_occasion=relaxed_occasion),
                    matchDetails=ExtensionMatchDetails(
                        colors=(
                            sorted({v.color for v in matching if v.color}) if intent.color else []
                        ),
                        sizes=sorted({v.size for v in matching if v.size}) if intent.size else [],
                        fit=intent.fit,
                        occasion=None if relaxed_occasion else intent.occasion,
                        audience=row.department if intent.audience else None,
                        imageMatchesColor=image_matches_color,
                    ),
                    variants=[
                        ExtensionVariantOut(
                            variantId=variant.external_variant_id,
                            color=variant.color,
                            size=variant.size,
                            available=variant.available,
                        )
                        for variant in display_variants
                    ],
                )
            )

        catalog_count = await self._catalog_count(brand.id)
        relaxed_filters = []
        if result.dropped_occasion:
            relaxed_filters.append("occasion")
        if result.dropped_category:
            relaxed_filters.append("category")
        relaxed = bool(relaxed_filters)

        return ExtensionSearchResponse(
            intent=intent,
            products=products,
            notice=(
                "Exact matches were unavailable; showing the closest relevant alternatives."
                if relaxed
                else None
            ),
            meta=ExtensionSearchMeta(
                storeDomain=_normalize_domain(brand.domain),
                fetchedCount=catalog_count,
                mappedCount=catalog_count,
                exactCount=0 if relaxed else len(products),
                catalogCapped=False,
                relaxed=relaxed,
                relaxedFilters=relaxed_filters,
                durationMs=int((time.monotonic() - started) * 1000),
            ),
        )
