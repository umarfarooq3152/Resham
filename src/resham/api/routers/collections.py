"""Collections API router — curated product collections over stored catalog."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from resham.config import get_settings
from resham.db.connection import get_session
from resham.repositories.collections_repo import CollectionsRepository
from resham.schemas.collection import CollectionProductsResponse, CollectionResponse
from resham.services.collections import resolve_collection_products
from resham.vectorstore.client import get_collection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collections", tags=["collections"])

_settings = get_settings()

# Every seeded collection filters purely on occasion/tags with no category
# (e.g. {"occasion": "eid", "budget_max": 50000}) — that combination gives
# eligibility.py's SQL query nothing to narrow on, so resolving one from
# scratch took 20-40s in practice (see search/eligibility.py's docstring on
# why a category-less search can't cheaply shrink the ~80k-row candidate
# set). A short TTL cache is the right tool specifically here, unlike for
# live chat search text: collections are a handful of static, admin-curated
# definitions, and the catalog itself only crawls every
# `crawl_interval_hours` (4 by default) — a few minutes of staleness is
# unnoticeable, and it turns every repeat page load into a cache hit instead
# of a full re-resolve.
_COLLECTION_CACHE_TTL_SECONDS = 900

if _settings.session_store_backend == "redis":
    import redis.asyncio as redis

    _redis_client: "redis.Redis | None" = redis.from_url(_settings.redis_url)
else:
    _redis_client = None


def _cache_key(collection_id: UUID, page: int, page_size: int) -> str:
    return f"collection:{collection_id}:{page}:{page_size}"


def get_vector_collection():
    return get_collection()


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    session: AsyncSession = Depends(get_session),
) -> list[CollectionResponse]:
    collections = await CollectionsRepository(session).get_all_active()
    return [CollectionResponse.model_validate(collection) for collection in collections]


@router.get("/{collection_id}", response_model=CollectionProductsResponse)
async def get_collection_detail(
    collection_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    vector_collection=Depends(get_vector_collection),
) -> CollectionProductsResponse:
    collection_row = await CollectionsRepository(session).get_by_id(collection_id)
    if collection_row is None or not collection_row.is_active:
        raise HTTPException(status_code=404, detail="Collection not found")

    cache_key = _cache_key(collection_id, page, page_size)
    if _redis_client is not None:
        try:
            cached = await _redis_client.get(cache_key)
            if cached:
                return CollectionProductsResponse.model_validate_json(cached)
        except Exception:
            logger.warning("Collection cache read failed for %s; resolving live", collection_id, exc_info=True)

    result = await resolve_collection_products(
        session,
        vector_collection,
        collection_row,
        page=page,
        page_size=page_size,
    )

    if _redis_client is not None:
        try:
            await _redis_client.setex(cache_key, _COLLECTION_CACHE_TTL_SECONDS, result.model_dump_json())
        except Exception:
            logger.warning("Collection cache write failed for %s", collection_id, exc_info=True)

    return result
