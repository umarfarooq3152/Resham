"""Chat turn orchestration: fast-path -> LLM -> merge -> RAG search.

Replaces Dhaaga's `_collect_candidate_products` (which called
`ProductCacheService.get_or_refresh` — a live Shopify fetch per brand per
request) with a call into `search/service.py`'s Postgres/Chroma-backed
eligibility+ranking+relax pipeline. No live network calls happen on the
request path at all — the LLM only ever extracts intent and writes the
conversational reply; it never sees or composes from the product list.
"""

import inspect
import logging
from uuid import UUID, uuid4

from chromadb.api.models.Collection import Collection
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.models.brand import Brand
from resham.llm.fallback import FallbackIntentProvider
from resham.nlp.brands import extract_requested_brands
from resham.nlp.diff_merge import merge_session_state
from resham.nlp.fast_path_classifier import classify, is_kids_request
from resham.nlp.garments import requested_formality, requested_tradition
from resham.repositories.chat_repo import ChatRepository
from resham.repositories.events_repo import SessionEventRepository
from resham.schemas.product import ProductSearchResponse
from resham.schemas.session import ChatTurnResponse, SessionState
from resham.search.eligibility import EligibilityFilters
from resham.search.relax import DEFAULT_RELAXABLE_FIELDS
from resham.search.service import build_query_text
from resham.search.service import search as run_search
from resham.session.store.base import SessionStore

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 40

_RELAXED_FIELD_LABELS = {"size": "size", "color": "color", "budget_max": "budget"}


def _filters_from_state(state: SessionState) -> EligibilityFilters:
    return EligibilityFilters(
        department=state.department,
        wants_kids=state.wants_kids,
        child_age_months=state.child_age_months,
        category=state.category,
        color=state.color_preference,
        size=state.size,
        budget_max=state.budget_max,
        brands=list(state.brands),
        excluded_brands=list(state.excluded),
    )


def _no_results_reply(state: SessionState) -> str:
    """A canned reply for a genuine zero-result miss — the LLM's own reply
    text (written before the search ran) is never shown here, since it may
    describe items the search then didn't actually return. By the time this
    fires, search/relax.py has already tried dropping occasion and every
    non-hard filter, so this means nothing close exists either — the
    message says so instead of suggesting relaxation that already ran."""
    if state.occasion:
        return (
            f"I couldn't find anything close for {state.occasion} even after loosening the "
            "filters — try a different product type, or tell me if department or age is off."
        )
    return (
        "I couldn't find anything close, even after loosening the filters — "
        "try a different product type, color, or budget range."
    )


def _relaxation_notice(
    effective_occasion: str | None,
    requested_occasion: str | None,
    effective_category: str | None,
    requested_category: str | None,
    dropped_filters: list[str],
) -> str | None:
    """Explain a relaxed result set in plain shopping language, rather than
    presenting the fallback as if it were an exact match — names exactly
    which filters were loosened so the shopper can tell it apart from an
    exact hit and put one back via the existing filter chips if they want."""
    if requested_category and effective_category != requested_category:
        return (
            f"Nothing in {requested_category} matched, "
            "so here are culturally similar alternatives."
        )

    dropped_occasion = requested_occasion and effective_occasion != requested_occasion
    labels = [_RELAXED_FIELD_LABELS[f] for f in dropped_filters if f in _RELAXED_FIELD_LABELS]

    if not dropped_occasion and not labels:
        return None
    if dropped_occasion and not labels:
        return f"Nothing tagged specifically for {requested_occasion}, so here's what's closest."
    loosened = " and ".join(labels)
    if dropped_occasion:
        return (
            f"Nothing tagged specifically for {requested_occasion}, and I loosened "
            f"{loosened} too — here's the closest match."
        )
    return f"No exact match for every detail, so I loosened {loosened} — here's the closest fit."


class SessionService:
    """Orchestrates one chat turn end to end."""

    def __init__(
        self,
        *,
        session_store: SessionStore,
        intent_provider: FallbackIntentProvider,
        db_session: AsyncSession,
        chroma_collection: Collection | None,
        chat_repo: ChatRepository,
        event_repo: SessionEventRepository,
        page_size: int = DEFAULT_PAGE_SIZE,
    ):
        self._store = session_store
        self._intent_provider = intent_provider
        self._db = db_session
        self._collection = chroma_collection
        self._chat_repo = chat_repo
        self._event_repo = event_repo
        self._page_size = page_size

    async def handle_turn(
        self,
        *,
        session_id: str | None,
        device_id: UUID | None,
        text: str,
        department: str | None,
        client_state: SessionState | None,
    ) -> ChatTurnResponse:
        session_id = session_id or str(uuid4())
        current_state = await self._store.get(session_id) or client_state or SessionState()
        if department and not current_state.department:
            current_state = current_state.model_copy(update={"department": department})
        last_results = await self._store.get_last_results(session_id)

        await self._chat_repo.add_message(session_id, "user", text, device_id=device_id)

        fast_match = classify(text, current_state, last_results)
        if fast_match is not None:
            diff = fast_match.diff
            turn_type = "fast_path"
            await self._event_repo.log_event(session_id, "turn_fast_path", device_id=device_id)
        else:
            diff = await self._intent_provider.extract(text, current_state)
            turn_type = "llm_extraction"
            await self._event_repo.log_event(session_id, "turn_llm_extraction", device_id=device_id)

        new_state = merge_session_state(current_state, diff)
        if is_kids_request(text):
            new_state = new_state.model_copy(update={"wants_kids": True})

        # Brand names are a deterministic catalog constraint, not an LLM
        # inference. Resolve only exact registry names/slugs and retain the
        # previous allow-list when this turn names no brand (normal refinements
        # such as "blue instead" must not broaden a brand-scoped search).
        brand_result = await self._db.execute(
            select(Brand.slug, Brand.name).where(Brand.is_active.is_(True))
        )
        active_brands = brand_result.all()
        # SQLAlchemy returns a synchronous list. This guard keeps the session
        # service tolerant of lightweight AsyncSession test doubles, whose
        # unconfigured ``.all()`` is itself an awaitable mock.
        if inspect.isawaitable(active_brands):
            active_brands = await active_brands
        if not isinstance(active_brands, (list, tuple)):
            active_brands = []
        requested_brands = extract_requested_brands(text, active_brands)
        if requested_brands:
            new_state = new_state.model_copy(update={"brands": requested_brands})

        filters = _filters_from_state(new_state)
        occasion_is_hard = "occasion" in new_state.hard_constraints

        # query_text mirrors what the browse endpoint reconstructs from
        # session state for a "load more" replay (build_query_text over
        # semantic_query + style_descriptors) rather than the raw chat
        # message — otherwise keyword scoring would rank this turn's page 1
        # differently from the browse-driven page 2+ that follows it, and
        # scrolling could silently skip or resurface a product between
        # pages. See search/service.py's build_query_text docstring.
        query_text = build_query_text(new_state.semantic_query, new_state.style_descriptors)

        result = await run_search(
            self._db,
            self._collection,
            filters,
            occasion=new_state.occasion,
            occasion_is_hard=occasion_is_hard,
            query_text=query_text,
            semantic_query=new_state.semantic_query or "",
            tradition=requested_tradition(new_state.style_descriptors),
            formality=requested_formality(new_state.style_descriptors),
            relaxable_fields=DEFAULT_RELAXABLE_FIELDS,
        )

        products = [row_to_pydantic_product(row) for row in result.products[: self._page_size]]

        if result.total == 0:
            reply = _no_results_reply(new_state)
        else:
            notice = _relaxation_notice(
                result.effective_occasion,
                new_state.occasion,
                result.effective_category,
                new_state.category,
                result.dropped_filters,
            )
            reply = notice or diff.assistant_reply

        await self._store.set(session_id, new_state)
        await self._store.set_last_results(session_id, products)
        await self._chat_repo.add_message(session_id, "assistant", reply, device_id=device_id)

        return ChatTurnResponse(
            session_id=session_id,
            reply=reply,
            session_state=new_state,
            filters={},
            products=ProductSearchResponse(
                items=products,
                total=result.total,
                page=1,
                page_size=self._page_size,
                has_more=result.total > len(products),
            ),
            turn_type=turn_type,
        )

    async def reset_session(self, session_id: str) -> ChatTurnResponse:
        fresh = SessionState()
        await self._store.set(session_id, fresh)
        await self._store.set_last_results(session_id, [])
        return ChatTurnResponse(
            session_id=session_id,
            reply="Filters cleared — what are you looking for?",
            session_state=fresh,
            filters={},
            products=ProductSearchResponse(
                items=[], total=0, page=1, page_size=self._page_size, has_more=False
            ),
            turn_type="fast_path",
        )
