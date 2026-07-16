"""Schemas for curated collections."""

from uuid import UUID

from pydantic import BaseModel

from resham.schemas.product import Product


class CollectionResponse(BaseModel):
    id: UUID
    title: str
    subtitle: str | None = None
    description: str | None = None
    image_url: str | None = None
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class CollectionProductsResponse(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    description: str | None = None
    image_url: str | None = None
    items: list[Product]
    total: int
    page: int
    page_size: int
    has_more: bool
