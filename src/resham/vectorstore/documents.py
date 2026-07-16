"""Builds Chroma document text + metadata from a durable product row.

Reuses `product_semantics.enrich_product_semantics` unmodified for the
document text — its `ProductSemantics.search_text` is already exactly the
right canonicalized concatenation (product family + audiences + occasions +
attributes + title + category + tags + truncated description). The same
`Product`-pydantic bridge pattern used in `catalog.repository` lets this
run against crawled/stored data with zero changes to the NLP layer.
"""

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.models.product import Product as ProductRow
from resham.nlp.product_semantics import enrich_product_semantics


def build_document(row: ProductRow) -> tuple[str, dict[str, str | int | float | bool]]:
    """Return (document_text, metadata) for one product row.

    Metadata is scalar-only (Chroma's `where` filter cannot match against
    lists) — colors/sizes are deliberately excluded here; that filtering
    happens against Postgres/`product_variants` in `search/eligibility.py`.
    """
    pydantic_product = row_to_pydantic_product(row)
    enriched = enrich_product_semantics(pydantic_product)
    document_text = enriched.semantics.search_text if enriched.semantics else pydantic_product.name

    # Image-derived category/color (resham.vision) supplements the text
    # pipeline for a product whose title/description under-describe what's
    # actually shown — appended, so a well-tagged product's embedding is
    # unaffected and this is a no-op until the product is classified.
    vision_terms = " ".join(filter(None, [row.vision_category, *row.vision_colors]))
    if vision_terms:
        document_text = f"{document_text} {vision_terms}"

    brand_slug = row.composite_key.split(":", 1)[0]
    metadata = {
        "brand_slug": brand_slug,
        "brand_id": str(row.brand_id),
        "department": row.department or "",
        "is_kids": row.is_kids,
        "product_family": (enriched.semantics.product_family if enriched.semantics else None) or "",
        "occasion": row.occasion or "",
        "min_price": float(row.min_price or 0),
        "max_price": float(row.max_price or 0),
        "in_stock": row.in_stock,
        "currency": row.currency,
        "content_hash": row.content_hash or "",
    }
    return document_text, metadata
