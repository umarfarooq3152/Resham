"""Stored-catalog product endpoints used by the web frontend."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.connection import get_session
from resham.db.models.product import Product as ProductRow
from resham.repositories.product_repo import ProductRepository
from resham.schemas.product import Product, ProductSearchResponse
from resham.search.eligibility import EligibilityFilters
from resham.search.service import search as run_search
from resham.vectorstore.client import get_collection

router = APIRouter(prefix="/products", tags=["products"])


def get_vector_collection():
    return get_collection()


def _build_query_text(query: str | None, tags: list[str]) -> str:
    terms = [term.strip() for term in [query or "", *tags] if term.strip()]
    return " ".join(terms)


def _paginate(rows: list[ProductRow], page: int, page_size: int) -> tuple[list[ProductRow], bool]:
    start = (page - 1) * page_size
    end = start + page_size
    return rows[start:end], end < len(rows)


@router.get("/search", response_model=ProductSearchResponse)
async def search_products(
    q: str | None = Query(None),
    category: str | None = Query(None),
    department: str | None = Query(None, pattern="^(men|women|unisex)$"),
    occasion: str | None = Query(None),
    color: str | None = Query(None),
    size: str | None = Query(None),
    tags: list[str] = Query(default_factory=list),
    wants_kids: bool = Query(False),
    child_age_months: int | None = Query(None, ge=0, le=215),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    vector_collection=Depends(get_vector_collection),
) -> ProductSearchResponse:
    query_text = _build_query_text(q, tags)
    result = await run_search(
        session,
        vector_collection,
        EligibilityFilters(
            department=department,
            wants_kids=wants_kids,
            child_age_months=child_age_months,
            category=category,
            color=color,
            size=size,
            budget_min=min_price,
            budget_max=max_price,
        ),
        occasion=occasion,
        query_text=query_text,
        semantic_query=query_text,
    )
    page_rows, has_more = _paginate(result.products, page, page_size)
    return ProductSearchResponse(
        items=[row_to_pydantic_product(row) for row in page_rows],
        total=result.total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/{product_id}", response_model=Product)
async def get_product(
    product_id: str,
    session: AsyncSession = Depends(get_session),
) -> Product:
    row = await ProductRepository(session).get_by_composite_key(product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row_to_pydantic_product(row)


@router.get("/{product_id}/alternatives", response_model=ProductSearchResponse)
async def get_product_alternatives(
    product_id: str,
    limit: int = Query(4, ge=1, le=20),
    page_size: int = Query(4, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
    vector_collection=Depends(get_vector_collection),
) -> ProductSearchResponse:
    row = await ProductRepository(session).get_by_composite_key(product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    stmt = (
        select(ProductRow)
        .where(
            ProductRow.id != row.id,
            ProductRow.in_stock.is_(True),
            ProductRow.removed_at.is_(None),
            ProductRow.is_kids.is_(row.is_kids),
        )
        .limit(200)
    )

    if row.department:
        stmt = stmt.where(ProductRow.department.in_([row.department, "unisex"]))
    if row.product_family:
        stmt = stmt.where(ProductRow.product_family == row.product_family)
    elif row.category:
        stmt = stmt.where(ProductRow.category == row.category)
    if row.occasion:
        stmt = stmt.where(ProductRow.occasion == row.occasion)

    candidates = list((await session.execute(stmt)).scalars().all())

    def _score(candidate: ProductRow) -> tuple[int, float]:
        tag_overlap = len(set(row.tags) & set(candidate.tags))
        color_overlap = len(set(row.colors) & set(candidate.colors))
        same_brand_penalty = 1 if candidate.brand_id == row.brand_id else 0
        price_gap = abs(float(candidate.min_price or 0) - float(row.min_price or 0))
        return (
            tag_overlap + color_overlap - same_brand_penalty,
            -price_gap,
        )

    candidates.sort(key=_score, reverse=True)
    trimmed = candidates[: min(limit, page_size)]
    return ProductSearchResponse(
        items=[row_to_pydantic_product(candidate) for candidate in trimmed],
        total=len(candidates),
        page=1,
        page_size=page_size,
        has_more=len(candidates) > len(trimmed),
    )
