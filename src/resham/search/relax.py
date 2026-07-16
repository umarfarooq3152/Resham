"""Automatic relaxation ladder — the "closest match" fallback for a genuine
zero-match, blended into a single strict-to-loose feed so scrolling past
the exact matches surfaces progressively broader ones instead of a hard
wall. Each tier re-runs the full eligibility -> ranking pass via
`search_once`, so eligibility.py's gate is never modified or bypassed —
every returned product still satisfies every filter it was actually
searched with in its own tier.

Tiers, in order: the exact request; occasion dropped (the original ladder's
one deliberate exception); size/color/budget peeled one at a time and kept
peeled (`_RELAXATION_ORDER`); then, only if literally nothing has matched
yet, a culturally appropriate alternative garment category via
`event_garments(occasion)`. Each new tier's products are appended after
everything already collected, deduped by id, up to `_MAX_BLENDED_RESULTS` —
so page 1 is always the best available match and later pages are
progressively looser, never a different mix of the same quality.

A field is only ever peeled if the caller marked it relaxable
(`relaxable_fields`). department/wants_kids/child_age_months are never part
of this ladder at all — they stay untouched in `filters` throughout, and
category only ever moves to an equivalent alternative (and only as an
absolute last resort), never to "any category".

`effective_occasion` / `effective_category` / `dropped_*` describe only the
*first* tier that produced a result — what the shopper-facing reply should
explain — not every tier blended in afterward purely for scroll depth.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from uuid import UUID

from resham.db.models.product import Product as ProductRow
from resham.nlp.pakistani_events import event_garments
from resham.search.eligibility import EligibilityFilters

SearchOnce = Callable[[EligibilityFilters, str | None], Awaitable[list[ProductRow]]]

# Priority order for automatic peeling — least disposable last, so a stated
# budget survives longer than size or color before it's the one relaxed.
_RELAXATION_ORDER: tuple[str, ...] = ("size", "color", "budget_max")

# The fields every caller offers to the ladder by default — the same set
# already exposed as manual "Any size / Any color / Any budget" relax chips
# in the web UI (ChatSearchScreen's relaxOptions), just applied
# automatically on a genuine zero-match instead of waiting for a click.
# Deliberately excludes department/wants_kids/child_age_months (auto-
# relaxing age could surface adult items on a "for my daughter" search) and
# category (which has its own culturally-aware alternative path below).
DEFAULT_RELAXABLE_FIELDS: frozenset[str] = frozenset({"size", "color", "budget_max"})

# Once the blended list reaches this size, no *further* tier is queried —
# it does not truncate a tier already in progress, so a single loose tier
# (e.g. dropping budget_max on a broad category) can still land well past
# this number in one shot. It only bounds how many additional search_once
# calls a zero/thin match chains through, giving several pages of "show
# more" (10 pages at the chat page size of 40, 4 at the browse endpoint's
# max of 100) before the ladder stops reaching for a looser tier.
_MAX_BLENDED_RESULTS = 200


@dataclass
class RelaxedResult:
    products: list[ProductRow]
    effective_occasion: str | None
    effective_category: str | None
    dropped_occasion: bool
    dropped_category: bool
    dropped_filters: list[str] = dataclass_field(default_factory=list)


def _has_value(filters: EligibilityFilters, field_name: str) -> bool:
    """Whether `field_name` (one of `_RELAXATION_ORDER`, which names match
    EligibilityFilters' own attributes) is actually set — clearing an
    already-None field is a no-op search-wise, and reporting it as
    "dropped" would tell the shopper we loosened a constraint they never
    stated (e.g. "I loosened size" when they never mentioned a size)."""
    return getattr(filters, field_name) is not None


def _clear(filters: EligibilityFilters, field_name: str) -> EligibilityFilters:
    if field_name == "size":
        return replace(filters, size=None)
    if field_name == "color":
        return replace(filters, color=None)
    if field_name == "budget_max":
        return replace(filters, budget_max=None)
    return filters


class _Blender:
    """Accumulates deduped products across tiers and records which tier
    first broke a zero-match, so the reply can name exactly that — not
    every tier blended in afterward purely to fill out the scroll."""

    def __init__(self) -> None:
        self._seen: set[UUID] = set()
        self.products: list[ProductRow] = []
        self.found_first_hit = False
        self.first_hit_occasion: str | None = None
        self.first_hit_category: str | None = None
        self.first_hit_dropped_occasion = False
        self.first_hit_dropped_category = False
        self.first_hit_dropped_filters: list[str] = []

    @property
    def full(self) -> bool:
        return len(self.products) >= _MAX_BLENDED_RESULTS

    def add_tier(
        self,
        products: list[ProductRow],
        *,
        occasion: str | None,
        category: str | None,
        dropped_occasion: bool,
        dropped_category: bool,
        dropped_filters: list[str],
    ) -> None:
        before = len(self.products)
        for row in products:
            if row.id not in self._seen:
                self._seen.add(row.id)
                self.products.append(row)
        if not self.found_first_hit and len(self.products) > before:
            self.found_first_hit = True
            self.first_hit_occasion = occasion
            self.first_hit_category = category
            self.first_hit_dropped_occasion = dropped_occasion
            self.first_hit_dropped_category = dropped_category
            self.first_hit_dropped_filters = list(dropped_filters)


async def search_with_relaxation(
    search_once: SearchOnce,
    filters: EligibilityFilters,
    occasion: str | None,
    *,
    occasion_is_hard: bool,
    relaxable_fields: frozenset[str] = frozenset(),
) -> RelaxedResult:
    """Blend a strict-to-loose feed: the exact request, then occasion
    dropped, then size/color/budget peeled cumulatively (per
    `relaxable_fields`), then — only if nothing at all has matched yet — a
    culturally equivalent category. Each tier's new products are appended
    after what's already collected, up to `_MAX_BLENDED_RESULTS`."""
    category = filters.category
    blender = _Blender()

    products = await search_once(filters, occasion)
    blender.add_tier(
        products, occasion=occasion, category=category,
        dropped_occasion=False, dropped_category=False, dropped_filters=[],
    )
    if blender.full:
        return _finish(blender, occasion, category)

    current_filters = filters
    current_occasion = occasion
    dropped: list[str] = []

    if occasion and not occasion_is_hard:
        dropped.append("occasion")
        current_occasion = None
        products = await search_once(current_filters, current_occasion)
        blender.add_tier(
            products, occasion=None, category=category,
            dropped_occasion=True, dropped_category=False, dropped_filters=list(dropped),
        )
        if blender.full:
            return _finish(blender, occasion, category)

    for field_name in _RELAXATION_ORDER:
        if field_name not in relaxable_fields:
            continue
        if _has_value(current_filters, field_name):
            dropped.append(field_name)
        current_filters = _clear(current_filters, field_name)
        products = await search_once(current_filters, current_occasion)
        blender.add_tier(
            products, occasion=current_occasion, category=category,
            dropped_occasion="occasion" in dropped, dropped_category=False,
            dropped_filters=list(dropped),
        )
        if blender.full:
            return _finish(blender, occasion, category)

    if not blender.found_first_hit and category and occasion:
        alternatives = [g for g in event_garments(occasion) if g != category]
        for alternative in alternatives:
            alt_filters = replace(current_filters, category=alternative)
            products = await search_once(alt_filters, None)
            blender.add_tier(
                products, occasion=None, category=alternative,
                dropped_occasion=True, dropped_category=True, dropped_filters=list(dropped),
            )
            if blender.full:
                break

    return _finish(blender, occasion, category)


def _finish(
    blender: _Blender, requested_occasion: str | None, requested_category: str | None
) -> RelaxedResult:
    if not blender.found_first_hit:
        return RelaxedResult([], requested_occasion, requested_category, False, False, [])
    return RelaxedResult(
        blender.products,
        blender.first_hit_occasion,
        blender.first_hit_category,
        blender.first_hit_dropped_occasion,
        blender.first_hit_dropped_category,
        blender.first_hit_dropped_filters,
    )
