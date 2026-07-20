"""Backend-mediated search endpoint for the Resham browser extension."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from resham.api.rate_limit import limiter
from resham.config import get_settings
from resham.db.connection import get_session
from resham.errors import ExternalServiceError
from resham.extension.service import ExtensionSearchError, ExtensionSearchService
from resham.llm.extension_provider import GroqExtensionProvider
from resham.llm.lmstudio_provider import LMStudioExtensionProvider
from resham.schemas.extension import ExtensionSearchRequest, ExtensionSearchResponse
from resham.vectorstore.client import get_collection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/extension", tags=["extension"])
settings = get_settings()
if settings.llm_provider.lower() == "lmstudio":
    provider = LMStudioExtensionProvider(
        settings.lmstudio_base_url,
        settings.lmstudio_api_key,
        settings.lmstudio_model,
        settings.lmstudio_timeout_seconds,
    )
else:
    provider = GroqExtensionProvider(settings.groq_api_key, settings.groq_model)


async def get_extension_search_service(
    db_session: AsyncSession = Depends(get_session),
) -> ExtensionSearchService:
    return ExtensionSearchService(
        session=db_session,
        collection=get_collection(),
        intent_provider=provider,
        result_limit=settings.extension_result_limit,
    )


@router.post("/search", response_model=ExtensionSearchResponse, response_model_by_alias=True)
@limiter.limit("10/minute")
async def search_store(
    request: Request,
    payload: ExtensionSearchRequest,
    service: ExtensionSearchService = Depends(get_extension_search_service),
) -> ExtensionSearchResponse:
    try:
        return await asyncio.wait_for(
            service.search(payload.query, payload.store_origin, payload.previous_intent),
            timeout=settings.extension_request_timeout_seconds,
        )
    except TimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "CATALOG_TIMEOUT",
                "message": "The search took too long. Please try again.",
            },
        ) from error
    except ExtensionSearchError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    except ExternalServiceError as error:
        logger.warning("Extension intent provider failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "PROVIDER_UNAVAILABLE",
                "message": "Resham's matching service is unavailable right now.",
            },
        ) from error
    except Exception as error:
        logger.exception("Extension search failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "The search could not be completed."},
        ) from error
