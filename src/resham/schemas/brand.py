"""Schemas for brand discovery responses."""

from uuid import UUID

from pydantic import BaseModel


class BrandResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    domain: str
    logo_url: str | None = None
    is_active: bool
    department: str

    class Config:
        from_attributes = True
