"""Occasion relaxation ladder — the one deliberate exception to "never
relax a hard constraint." Occasion is treated as a soft signal: on zero
exact matches, first drop it, then (if category itself isn't a hard
constraint) try culturally appropriate alternative garment categories via
`event_garments(occasion)`. Color/size/budget/department/age are never
touched here — they live in the filters passed through untouched.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from resham.db.models.product import Product as ProductRow
from resham.nlp.pakistani_events import event_garments
from resham.search.eligibility import EligibilityFilters

SearchOnce = Callable[[EligibilityFilters, str | None], Awaitable[list[ProductRow]]]


@dataclass
class RelaxedResult:
    products: list[ProductRow]
    effective_occasion: str | None
    effective_category: str | None
    dropped_occasion: bool
    dropped_category: bool


async def search_with_relaxation(
    search_once: SearchOnce,
    filters: EligibilityFilters,
    occasion: str | None,
    *,
    occasion_is_hard: bool,
) -> RelaxedResult:
    """Try the exact request first; relax only on a genuine zero-match miss."""
    category = filters.category
    products = await search_once(filters, occasion)
    if products or not occasion or occasion_is_hard:
        return RelaxedResult(products, occasion, category, False, False)

    products = await search_once(filters, None)
    if products:
        return RelaxedResult(products, None, category, True, False)

    if not category:
        return RelaxedResult([], occasion, category, False, False)

    alternatives = [g for g in event_garments(occasion) if g != category]
    for alternative in alternatives:
        alt_filters = replace(filters, category=alternative)
        products = await search_once(alt_filters, None)
        if products:
            return RelaxedResult(products, None, alternative, True, True)

    return RelaxedResult([], occasion, category, False, False)
