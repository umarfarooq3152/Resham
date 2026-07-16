from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.connection import get_session
from resham.db.models.brand import Brand
from resham.db.models.crawl_run import CrawlRun
from resham.db.models.product import Product
from resham.schemas.admin import BrandCatalogSummary, CatalogSummaryResponse, CrawlRunResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/catalog/summary", response_model=CatalogSummaryResponse)
async def catalog_summary(
    session: AsyncSession = Depends(get_session),
) -> CatalogSummaryResponse:
    total_products = await session.scalar(select(func.count()).select_from(Product)) or 0
    in_stock_products = await session.scalar(
        select(func.count()).select_from(Product).where(Product.in_stock.is_(True))
    ) or 0
    with_occasion = await session.scalar(
        select(func.count()).select_from(Product).where(Product.occasion.is_not(None))
    ) or 0
    with_product_family = (
        await session.scalar(
            select(func.count()).select_from(Product).where(Product.product_family.is_not(None))
        )
        or 0
    )
    embedded_products = (
        await session.scalar(
            select(func.count()).select_from(Product).where(Product.embedded_at.is_not(None))
        )
        or 0
    )
    brand_rows = list(
        (
            await session.execute(
                select(Brand.slug, func.count(Product.id))
                .join(Product, Product.brand_id == Brand.id)
                .group_by(Brand.slug)
                .order_by(Brand.slug)
            )
        ).all()
    )
    return CatalogSummaryResponse(
        total_products=total_products,
        in_stock_products=in_stock_products,
        out_of_stock_products=total_products - in_stock_products,
        with_occasion=with_occasion,
        with_product_family=with_product_family,
        embedded_products=embedded_products,
        brands=[BrandCatalogSummary(slug=slug, products=count) for slug, count in brand_rows],
    )


@router.get("/crawl-runs", response_model=list[CrawlRunResponse])
async def recent_crawl_runs(
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[CrawlRunResponse]:
    rows = list(
        (
            await session.execute(
                select(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(limit)
            )
        ).scalars().all()
    )
    return [
        CrawlRunResponse(
            id=str(row.id),
            status=row.status,
            trigger=row.trigger,
            started_at=row.started_at,
            finished_at=row.finished_at,
            stats=row.stats,
        )
        for row in rows
    ]
