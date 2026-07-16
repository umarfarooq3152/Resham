"""Resolution of curated collections against the persisted catalog."""

from chromadb.api.models.Collection import Collection as ChromaCollection
from sqlalchemy.ext.asyncio import AsyncSession

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.models.collections import Collection as CollectionRow
from resham.schemas.collection import CollectionProductsResponse
from resham.search.eligibility import EligibilityFilters
from resham.search.service import search as run_search


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def build_collection_filters(filter_definition: dict) -> tuple[EligibilityFilters, dict]:
    meta = {
        "query_text": str(filter_definition.get("query") or "").strip(),
        "semantic_query": str(
            filter_definition.get("semantic_query") or filter_definition.get("query") or ""
        ).strip(),
        "occasion": filter_definition.get("occasion"),
        "occasion_is_hard": bool(filter_definition.get("occasion_is_hard", False)),
        "tags": _string_list(filter_definition.get("tags")),
    }
    filters = EligibilityFilters(
        department=filter_definition.get("department"),
        wants_kids=bool(filter_definition.get("wants_kids", False)),
        child_age_months=filter_definition.get("child_age_months"),
        category=filter_definition.get("category"),
        color=next(iter(_string_list(filter_definition.get("colors"))), None),
        size=filter_definition.get("size"),
        budget_min=filter_definition.get("min_price") or filter_definition.get("budget_min"),
        budget_max=filter_definition.get("max_price") or filter_definition.get("budget_max"),
        brands=_string_list(filter_definition.get("brands")),
        excluded_brands=_string_list(filter_definition.get("excluded_brands")),
    )
    return filters, meta


async def resolve_collection_products(
    session: AsyncSession,
    vector_collection: ChromaCollection | None,
    collection_row: CollectionRow,
    *,
    page: int,
    page_size: int,
) -> CollectionProductsResponse:
    filters, meta = build_collection_filters(collection_row.filter_definition or {})
    result = await run_search(
        session,
        vector_collection,
        filters,
        occasion=meta["occasion"],
        occasion_is_hard=meta["occasion_is_hard"],
        query_text=meta["query_text"],
        semantic_query=meta["semantic_query"],
    )

    rows = result.products
    if meta["tags"]:
        required_tags = {tag.lower() for tag in meta["tags"]}
        rows = [
            row for row in rows
            if required_tags.issubset({tag.lower() for tag in row.tags + row.shopify_tags})
        ]

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    items = [row_to_pydantic_product(row) for row in rows[start:end]]
    return CollectionProductsResponse(
        id=str(collection_row.id),
        title=collection_row.title,
        subtitle=collection_row.subtitle,
        description=collection_row.description,
        image_url=collection_row.image_url,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=end < total,
    )
