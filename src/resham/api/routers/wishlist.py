"""Wishlist API router — manage persisted device/account wishlists."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.connection import get_session
from resham.dependencies import get_current_user_id_optional
from resham.repositories.device_repo import DeviceRepository
from resham.repositories.product_repo import ProductRepository
from resham.repositories.wishlist_repo import WishlistRepository
from resham.schemas.wishlist import WishlistItemResponse, WishlistResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wishlist", tags=["wishlist"])


def _mask(device_id: UUID) -> str:
    return f"{str(device_id)[:8]}..."


@router.get("", response_model=WishlistResponse)
async def get_wishlist(
    device_id: UUID = Header(..., alias="X-Device-Id"),
    user_id: Optional[UUID] = Depends(get_current_user_id_optional),
    session: AsyncSession = Depends(get_session),
) -> WishlistResponse:
    await DeviceRepository(session).get_or_create(device_id)

    wishlist_repo = WishlistRepository(session)
    items = await (
        wishlist_repo.get_all_for_user(user_id) if user_id else wishlist_repo.get_all(device_id)
    )

    product_rows = await ProductRepository(session).get_by_ids([item.product_id for item in items])
    products_by_id = {row.id: row for row in product_rows}
    hydrated_items = [
        WishlistItemResponse(
            product=row_to_pydantic_product(products_by_id[item.product_id]),
            added_at=item.created_at,
        )
        for item in items
        if item.product_id in products_by_id
    ]
    logger.debug(
        "Retrieved wishlist for device %s: %d items",
        _mask(device_id),
        len(hydrated_items),
    )
    return WishlistResponse(device_id=device_id, items=hydrated_items, total=len(hydrated_items))


@router.post("/{product_id}", response_model=dict)
async def add_to_wishlist(
    product_id: str,
    device_id: UUID = Header(..., alias="X-Device-Id"),
    user_id: Optional[UUID] = Depends(get_current_user_id_optional),
    session: AsyncSession = Depends(get_session),
) -> dict:
    device_repo = DeviceRepository(session)
    await device_repo.get_or_create(device_id)

    product = await ProductRepository(session).get_by_composite_key(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    wishlist_repo = WishlistRepository(session)
    if user_id:
        if await wishlist_repo.exists_for_user(user_id, product.id):
            return {"success": False, "message": "Already in wishlist"}
        await wishlist_repo.add_for_user(user_id, device_id, product.id)
    else:
        if await wishlist_repo.exists(device_id, product.id):
            return {"success": False, "message": "Already in wishlist"}
        await wishlist_repo.add(device_id, product.id)

    await device_repo.update_last_seen(device_id)
    await session.commit()
    logger.info("Added %s to wishlist for device %s", product_id, _mask(device_id))
    return {"success": True, "message": "Added to wishlist"}


@router.delete("/{product_id}", response_model=dict)
async def remove_from_wishlist(
    product_id: str,
    device_id: UUID = Header(..., alias="X-Device-Id"),
    user_id: Optional[UUID] = Depends(get_current_user_id_optional),
    session: AsyncSession = Depends(get_session),
) -> dict:
    device_repo = DeviceRepository(session)
    await device_repo.get_or_create(device_id)

    product = await ProductRepository(session).get_by_composite_key(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    wishlist_repo = WishlistRepository(session)
    if user_id:
        await wishlist_repo.remove_for_user(user_id, product.id)
    else:
        await wishlist_repo.remove(device_id, product.id)

    await device_repo.update_last_seen(device_id)
    await session.commit()
    logger.info("Removed %s from wishlist for device %s", product_id, _mask(device_id))
    return {"success": True, "message": "Removed from wishlist"}
