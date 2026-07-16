"""Collections API router — curated product collections over stored catalog."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.connection import get_session
from resham.repositories.collections_repo import CollectionsRepository
from resham.schemas.collection import CollectionProductsResponse, CollectionResponse
from resham.services.collections import resolve_collection_products
from resham.vectorstore.client import get_collection

router = APIRouter(prefix="/collections", tags=["collections"])


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
    return await resolve_collection_products(
        session,
        vector_collection,
        collection_row,
        page=page,
        page_size=page_size,
    )
