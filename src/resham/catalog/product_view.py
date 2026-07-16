"""Bridges a durable `products` row to the API-facing pydantic `Product`
schema, so the existing NLP layer (product_semantics, keyword_matcher,
pakistani_events) runs unmodified against crawled/stored data — the same
trick used at ingestion time in `catalog.repository`."""

from resham.db.models.product import Product as ProductRow
from resham.schemas.product import Product as PydanticProduct


def row_to_pydantic_product(row: ProductRow) -> PydanticProduct:
    return PydanticProduct(
        id=row.composite_key,
        name=row.title,
        description=row.description_text,
        price=float(row.min_price or 0),
        colors=row.colors,
        color_images=row.color_images,
        sizes=row.sizes,
        occasion=row.occasion,
        category=row.category,
        tags=row.tags,
        shopify_tags=row.shopify_tags,
        is_kids=row.is_kids,
        department=row.department,
        age_ranges_months=[tuple(r) for r in row.age_ranges_months],
        image=row.primary_image_url or "",
        secondaryImage=row.secondary_image_url,
        product_url=row.product_url or "",
    )
