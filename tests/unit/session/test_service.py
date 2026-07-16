"""Regression test for the semantic_query fallback bug: a fully-structured,
fast-path turn must not fall back to the raw query text as its semantic_query,
or vector ranking would run on every request instead of only when the LLM
path has genuinely produced descriptive residue."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from resham.schemas.session import IntentExtractionResult
from resham.search.service import SearchResult
from resham.session.service import SessionService
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


def _build_service(intent_provider=None) -> SessionService:
    return SessionService(
        session_store=MemorySessionStore(),
        intent_provider=intent_provider or AsyncMock(),
        db_session=AsyncMock(),
        chroma_collection=None,
        chat_repo=AsyncMock(),
        event_repo=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_fast_path_structured_query_passes_empty_semantic_query():
    service = _build_service()

    with patch(
        "resham.session.service.run_search", new=AsyncMock(return_value=_fake_result())
    ) as mock_search:
        await service.handle_turn(
            session_id=str(uuid4()),
            device_id=None,
            text="blue kurta size M under 5000",
            department=None,
            client_state=None,
        )

    assert mock_search.call_args.kwargs["semantic_query"] == ""


@pytest.mark.asyncio
async def test_llm_path_with_descriptive_residue_passes_real_semantic_query():
    fake_provider = AsyncMock()
    fake_provider.extract.return_value = IntentExtractionResult(
        assistant_reply="Here are some elegant options.",
        semantic_query="something elegant for a wedding",
    )
    service = _build_service(intent_provider=fake_provider)

    with patch(
        "resham.session.service.run_search", new=AsyncMock(return_value=_fake_result())
    ) as mock_search:
        await service.handle_turn(
            session_id=str(uuid4()),
            device_id=None,
            text="something elegant for a wedding",
            department=None,
            client_state=None,
        )

    assert mock_search.call_args.kwargs["semantic_query"] == "something elegant for a wedding"
