"""Session/chat API router — the core conversational search endpoint."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from resham.config import get_settings
from resham.db.connection import get_session
from resham.llm.fallback import FallbackIntentProvider
from resham.llm.gemini_provider import GeminiIntentProvider
from resham.llm.groq_provider import GroqIntentProvider
from resham.repositories.chat_repo import ChatRepository
from resham.repositories.device_repo import DeviceRepository
from resham.repositories.events_repo import SessionEventRepository
from resham.schemas.session import ChatTurnRequest, ChatTurnResponse, SessionResetRequest
from resham.session.service import SessionService
from resham.session.store.memory_store import MemorySessionStore
from resham.session.store.redis_store import RedisSessionStore
from resham.vectorstore.client import get_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])

# Providers/clients are stateless — safe to build once at import time and
# reuse across requests, same as Dhaaga's session router.
_settings = get_settings()
_fallback_provider = FallbackIntentProvider(
    primary=GeminiIntentProvider(_settings.gemini_api_key, _settings.gemini_model),
    fallback=GroqIntentProvider(_settings.groq_api_key, _settings.groq_model),
    primary_timeout_seconds=_settings.gemini_timeout_seconds,
    fallback_timeout_seconds=_settings.groq_timeout_seconds,
    primary_rate_limit_cooldown_seconds=_settings.gemini_rate_limit_cooldown_seconds,
)
_chroma_collection = get_collection()

if _settings.session_store_backend == "redis":
    import redis.asyncio as redis

    _redis_client = redis.from_url(_settings.redis_url)
    _session_store = RedisSessionStore(_redis_client, ttl_hours=_settings.session_ttl_hours)
else:
    _session_store = MemorySessionStore()


async def get_session_service(
    db_session: AsyncSession = Depends(get_session),
) -> SessionService:
    return SessionService(
        session_store=_session_store,
        intent_provider=_fallback_provider,
        db_session=db_session,
        chroma_collection=_chroma_collection,
        chat_repo=ChatRepository(db_session),
        event_repo=SessionEventRepository(db_session),
    )


@router.post("/message", response_model=ChatTurnResponse)
async def send_message(
    payload: ChatTurnRequest,
    device_id: Optional[UUID] = Header(None, alias="X-Device-Id"),
    db_session: AsyncSession = Depends(get_session),
    service: SessionService = Depends(get_session_service),
) -> ChatTurnResponse:
    """Send a chat turn: text in, structured intent extraction + RAG search out.

    X-Device-Id is optional — chat works anonymously; when present, messages
    are attributed to that device for the chat log and analytics events.
    """
    try:
        if device_id is not None:
            await DeviceRepository(db_session).get_or_create(device_id)
        result = await service.handle_turn(
            session_id=payload.session_id,
            device_id=device_id,
            text=payload.query,
            department=payload.department,
            client_state=payload.session_state,
        )
        await db_session.commit()
        return result
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Session message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process message")


@router.post("/reset", response_model=ChatTurnResponse)
async def reset_session(
    payload: SessionResetRequest,
    db_session: AsyncSession = Depends(get_session),
    service: SessionService = Depends(get_session_service),
) -> ChatTurnResponse:
    """Clear a session's filters/state back to fresh — backs the "Clear All" action."""
    try:
        result = await service.reset_session(payload.session_id)
        await db_session.commit()
        return result
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Session reset failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reset session")
