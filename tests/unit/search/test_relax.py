"""Unit coverage for search/relax.py's ladder against a stubbed search_once
— no DB needed, since the point here is the ladder's own bookkeeping
(which fields get reported as "dropped", tier blending), not eligibility
SQL semantics (that's tests/integration/test_search_eligibility.py)."""

from types import SimpleNamespace

import pytest
from resham.search.eligibility import EligibilityFilters
from resham.search.relax import DEFAULT_RELAXABLE_FIELDS, search_with_relaxation


def _row(id_):
    return SimpleNamespace(id=id_)


@pytest.mark.asyncio
async def test_dropped_filters_never_names_a_field_the_shopper_never_set():
    """A shopper who never mentioned a size shouldn't be told "I loosened
    size" just because the ladder's fixed field order tried clearing it —
    clearing an already-None field changes nothing about the search."""
    filters = EligibilityFilters(category="kurta", budget_max=1000)  # size, color unset

    async def fake_search_once(current_filters, occasion):
        if current_filters.budget_max is None:
            return [_row(1)]
        return []

    result = await search_with_relaxation(
        fake_search_once, filters, "eid",
        occasion_is_hard=False, relaxable_fields=frozenset({"budget_max"}),
    )

    assert result.products == [_row(1)]
    assert "size" not in result.dropped_filters
    assert "color" not in result.dropped_filters
    assert "budget_max" in result.dropped_filters


@pytest.mark.asyncio
async def test_dropped_filters_names_a_field_that_actually_had_a_value():
    filters = EligibilityFilters(category="kurta", size="M", budget_max=1000)

    async def fake_search_once(current_filters, occasion):
        if current_filters.size is None:
            return [_row(1)]
        return []

    result = await search_with_relaxation(
        fake_search_once, filters, "eid",
        occasion_is_hard=False, relaxable_fields=DEFAULT_RELAXABLE_FIELDS,
    )

    assert "size" in result.dropped_filters


@pytest.mark.asyncio
async def test_no_relaxation_reported_when_the_exact_request_already_matches():
    filters = EligibilityFilters(category="kurta", size="M")

    async def fake_search_once(current_filters, occasion):
        return [_row(1)]

    result = await search_with_relaxation(
        fake_search_once, filters, "eid",
        occasion_is_hard=False, relaxable_fields=DEFAULT_RELAXABLE_FIELDS,
    )

    assert result.dropped_filters == []
    assert result.dropped_occasion is False
