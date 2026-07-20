"""Stored-catalog product endpoints used by the web frontend."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.catalog.product_view import row_to_pydantic_product
from resham.config import get_settings
from resham.db.connection import get_session
from resham.db.models.brand import Brand
from resham.db.models.product import Product as ProductRow
from resham.db.models.product_variant import ProductVariant as VariantRow
from resham.repositories.product_repo import ProductRepository
from resham.schemas.product import Product, ProductSearchResponse, VisualSearchResponse
from resham.search.eligibility import EligibilityFilters
from resham.search.relax import DEFAULT_RELAXABLE_FIELDS
from resham.search.service import build_query_text
from resham.search.service import search as run_search
from resham.vectorstore.client import get_collection
from resham.vision.query import describe_search_image

router = APIRouter(prefix="/products", tags=["products"])
MAX_VISUAL_SEARCH_IMAGE_BYTES = 8 * 1024 * 1024


def get_vector_collection():
    return get_collection()


def _paginate(rows: list[ProductRow], page: int, page_size: int) -> tuple[list[ProductRow], bool]:
    start = (page - 1) * page_size
    end = start + page_size
    return rows[start:end], end < len(rows)


@router.post("/visual-search", response_model=VisualSearchResponse)
async def visual_search_products(
    image: UploadFile = File(...),
    department: str | None = Query(None, pattern="^(men|women|unisex)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    vector_collection=Depends(get_vector_collection),
) -> VisualSearchResponse:
    """Search from a reference image using exactly one image-to-text call.

    The resulting text is passed through the normal catalog eligibility and
    ranking pipeline; this endpoint does not create a second image index.
    """
    mime_type = (image.content_type or "").lower()
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image.")
    image_bytes = await image.read(MAX_VISUAL_SEARCH_IMAGE_BYTES + 1)
    if not image_bytes or len(image_bytes) > MAX_VISUAL_SEARCH_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be between 1 byte and 8 MB.")

    settings = get_settings()
    intent = await describe_search_image(
        image_bytes,
        mime_type=mime_type,
        api_key=settings.gemini_api_key,
        model=settings.gemini_vision_model,
    )
    if intent is None:
        raise HTTPException(
            status_code=502, detail="The image could not be analyzed. Please try again."
        )

    result = await run_search(
        session,
        vector_collection,
        EligibilityFilters(department=department, category=intent.category, color=intent.color),
        occasion=None,
        query_text=intent.query,
        semantic_query=intent.query,
        relaxable_fields=DEFAULT_RELAXABLE_FIELDS,
    )
    page_rows, has_more = _paginate(result.products, page, page_size)
    return VisualSearchResponse(
        items=[row_to_pydantic_product(row) for row in page_rows],
        total=result.total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        query=intent.query,
        category=intent.category,
        color=intent.color,
    )


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
    query_text = build_query_text(q, tags)
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
        relaxable_fields=DEFAULT_RELAXABLE_FIELDS,
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

    # Explicit queries, not the lazy `row.variants`/no ORM brand relationship
    # — see product_view.py's row_to_pydantic_product docstring.
    variants = list(
        (await session.execute(select(VariantRow).where(VariantRow.product_id == row.id)))
        .scalars()
        .all()
    )
    brand = await session.get(Brand, row.brand_id)

    return row_to_pydantic_product(
        row, variants=variants, brand_domain=brand.domain if brand else None
    )


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
