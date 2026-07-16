"""Unit coverage for the auto-relaxation glue in session/service.py: that
handle_turn always offers size/color/budget to search/relax.py's ladder
(matching the browse endpoint, so a "load more" replay never diverges from
the chat turn that produced it), and how a relaxed result is explained back
to the shopper."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from resham.schemas.session import IntentExtractionResult
from resham.search.relax import DEFAULT_RELAXABLE_FIELDS
from resham.search.service import SearchResult
from resham.session.service import SessionService, _relaxation_notice
from resham.session.store.memory_store import MemorySessionStore


def _fake_result() -> SearchResult:
    return SearchResult(
        products=[],
        total=0,
        effective_occasion=None,
        effective_category=None,
        dropped_occasion=False,
        dropped_category=False,
    )


@pytest.mark.asyncio
async def test_handle_turn_always_offers_size_color_budget_to_the_relaxation_ladder():
    """No field is excluded based on hard_constraints — an explicit "must be
    size M" still surfaces a closest match rather than a dead end; see
    search/relax.py's DEFAULT_RELAXABLE_FIELDS docstring for why."""
    fake_provider = AsyncMock()
    fake_provider.extract.return_value = IntentExtractionResult(
        assistant_reply="Here are some options.",
        category="polo shirt",
        color_preference="red",
        size="XXL",
        budget_max=1000,
        hard_constraints=["category", "color_preference", "size", "budget_max"],
    )
    service = SessionService(
        session_store=MemorySessionStore(),
        intent_provider=fake_provider,
        db_session=AsyncMock(),
        chroma_collection=None,
        chat_repo=AsyncMock(),
        event_repo=AsyncMock(),
    )

    with patch(
        "resham.session.service.run_search", new=AsyncMock(return_value=_fake_result())
    ) as mock_search:
        await service.handle_turn(
            session_id=str(uuid4()),
            device_id=None,
            text="red polo shirt size XXL under 1000",
            department=None,
            client_state=None,
        )

    assert mock_search.call_args.kwargs["relaxable_fields"] == DEFAULT_RELAXABLE_FIELDS


def test_relaxation_notice_is_none_when_nothing_was_dropped():
    notice = _relaxation_notice(
        effective_occasion="eid", requested_occasion="eid",
        effective_category="kurta", requested_category="kurta",
        dropped_filters=[],
    )

    assert notice is None


def test_relaxation_notice_names_the_dropped_filters():
    notice = _relaxation_notice(
        effective_occasion=None, requested_occasion=None,
        effective_category="kurta", requested_category="kurta",
        dropped_filters=["size", "budget_max"],
    )

    assert notice is not None
    assert "size" in notice
    assert "budget" in notice


def test_relaxation_notice_mentions_occasion_drop_without_filter_labels():
    notice = _relaxation_notice(
        effective_occasion=None, requested_occasion="eid",
        effective_category="kurta", requested_category="kurta",
        dropped_filters=["occasion"],
    )

    assert notice == "Nothing tagged specifically for eid, so here's what's closest."


def test_relaxation_notice_prefers_the_category_swap_explanation():
    notice = _relaxation_notice(
        effective_occasion=None, requested_occasion="eid",
        effective_category="shawl", requested_category="kurta",
        dropped_filters=["occasion", "size"],
    )

    assert notice == "Nothing in kurta matched, so here are culturally similar alternatives."
