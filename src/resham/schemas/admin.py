"""Schemas for admin/status endpoints."""

from datetime import datetime

from pydantic import BaseModel


class BrandCatalogSummary(BaseModel):
    slug: str
    products: int


class CatalogSummaryResponse(BaseModel):
    total_products: int
    in_stock_products: int
    out_of_stock_products: int
    with_occasion: int
    with_product_family: int
    embedded_products: int
    brands: list[BrandCatalogSummary]


class CrawlRunResponse(BaseModel):
    id: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict
