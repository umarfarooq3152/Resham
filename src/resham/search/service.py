"""Orchestrates eligibility -> ranking -> relax -> re-validate — the shared
RAG-aware search core used by both the session chat endpoint and the
extension endpoint, so the two surfaces can never silently diverge on what
counts as a match.
"""

import logging
from dataclasses import dataclass, field

from chromadb.api.models.Collection import Collection
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.product import Product as ProductRow
from resham.search.eligibility import EligibilityFilters, eligible_products
from resham.search.ranking import rank_products
from resham.search.relax import search_with_relaxation

logger = logging.getLogger(__name__)


def build_query_text(query: str | None, tags: list[str]) -> str:
    """The single definition of "query text for keyword scoring" shared by
    both search surfaces (session/service.py's chat turn and the
    products.py browse/pagination endpoint). Chat's `loadMore` replays a
    later page through the browse endpoint using session state alone (see
    web/src/hooks/useSessionChat.ts's `buildPaginationQuery`), so if the two
    callers ever computed `query_text` differently, keyword scoring would
    rank chat's page 1 and the browse-driven page 2+ differently enough
    that "scroll for progressively looser results" could silently skip or
    resurface a product between pages."""
    terms = [term.strip() for term in [query or "", *tags] if term.strip()]
    return " ".join(terms)


class EligibilityViolation(RuntimeError):
    """Raised if ranking ever returns a product eligibility didn't allow.

    This is the explicit, always-on guarantee behind "vector ranking never
    leaks an ineligible card" — not just a test assertion.
    """


@dataclass
class SearchResult:
    products: list[ProductRow]
    total: int
    effective_occasion: str | None
    effective_category: str | None
    dropped_occasion: bool
    dropped_category: bool
    dropped_filters: list[str] = field(default_factory=list)


def _assert_subset(ranked: list[ProductRow], eligible: list[ProductRow]) -> None:
    eligible_ids = {row.id for row in eligible}
    for row in ranked:
        if row.id not in eligible_ids:
            raise EligibilityViolation(f"Ranked product {row.id} was not in the eligible set")


async def search(
    session: AsyncSession,
    collection: Collection | None,
    filters: EligibilityFilters,
    *,
    occasion: str | None,
    occasion_is_hard: bool = False,
    query_text: str = "",
    semantic_query: str = "",
    tradition: str | None = None,
    formality: str | None = None,
    relaxable_fields: frozenset[str] = frozenset(),
) -> SearchResult:
    """The shared search entrypoint: gate with eligibility.py (hard filters
    only), order with ranking.py (vector + rule-based, never widens the
    set), recover from a genuine zero-match with relax.py — occasion always,
    plus whichever of size/color/budget_max the caller marks relaxable.
    """

    async def _search_once(
        current_filters: EligibilityFilters, current_occasion: str | None
    ) -> list[ProductRow]:
        eligible = await eligible_products(session, current_filters)
        ranked = await rank_products(
            eligible,
            query_text=query_text,
            occasion=current_occasion,
            semantic_query=semantic_query,
            color=current_filters.color,
            tradition=tradition,
            formality=formality,
            collection=collection,
        )
        _assert_subset(ranked, eligible)
        return ranked

    relaxed = await search_with_relaxation(
        _search_once,
        filters,
        occasion,
        occasion_is_hard=occasion_is_hard,
        relaxable_fields=relaxable_fields,
    )

    return SearchResult(
        products=relaxed.products,
        total=len(relaxed.products),
        effective_occasion=relaxed.effective_occasion,
        effective_category=relaxed.effective_category,
        dropped_occasion=relaxed.dropped_occasion,
        dropped_category=relaxed.dropped_category,
        dropped_filters=relaxed.dropped_filters,
    )
