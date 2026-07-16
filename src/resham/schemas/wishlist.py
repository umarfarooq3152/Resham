"""Schemas for wishlist responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from resham.schemas.product import Product


class WishlistItemResponse(BaseModel):
    product: Product
    added_at: datetime


class WishlistResponse(BaseModel):
    device_id: UUID
    items: list[WishlistItemResponse]
    total: int
