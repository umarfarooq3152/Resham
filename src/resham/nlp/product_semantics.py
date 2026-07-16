"""Versioned semantic enrichment for catalog products.

This layer canonicalizes merchant metadata once at ingestion/cache load. It is
not a user-language parser: conversational semantics remain the LLM's job.
"""

import re

from resham.nlp.apparel_classification import extract_classification_request
from resham.nlp.garments import extract_garment_descriptors, extract_primary_garment
from resham.nlp.pakistani_events import infer_product_event
from resham.schemas.product import Product, ProductSemantics


SEMANTIC_PROFILE_VERSION = "catalog-semantic-v1"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def enrich_product_semantics(product: Product) -> Product:
    """Attach a compact canonical profile, preserving the Product identity."""
    core_source = " ".join((
        product.name,
        product.category or "",
        " ".join(product.shopify_tags),
        " ".join(product.tags),
    ))
    family = (
        extract_primary_garment(product.category or "")
        or extract_primary_garment(product.name)
        or extract_primary_garment(" ".join(product.shopify_tags))
    )
    classification = extract_classification_request(core_source)
    attributes = list(dict.fromkeys(filter(None, (
        *product.tags,
        *extract_garment_descriptors(core_source),
        classification.formality,
        classification.tradition,
        *[color.lower() for color in product.colors if color.lower() != "default"],
    ))))
    audience = [product.department] if product.department else []
    if product.is_kids:
        audience.append("kids")
    # Product occasion is already classified by the ingestion tagger. Only
    # inspect raw metadata for callers that enrich an untagged Product.
    event = product.occasion or infer_product_event(product)
    occasions = [event.lower()] if event else []

    # Put canonical concepts first; descriptions are truncated because long
    # merchant care instructions add noise but little retrieval value.
    semantic_text = _clean(" ".join(filter(None, (
        family,
        " ".join(audience),
        " ".join(occasions),
        " ".join(attributes),
        product.name,
        product.category,
        " ".join(product.shopify_tags),
        (product.description or "")[:600],
    )))).lower()
    product.semantics = ProductSemantics(
        version=SEMANTIC_PROFILE_VERSION,
        product_family=family,
        audiences=list(dict.fromkeys(audience)),
        occasions=list(dict.fromkeys(occasions)),
        attributes=attributes,
        search_text=semantic_text,
    )
    return product


def ensure_product_semantics(product: Product) -> Product:
    if (
        not product.semantics
        or product.semantics.version != SEMANTIC_PROFILE_VERSION
        or not product.semantics.search_text
    ):
        return enrich_product_semantics(product)
    return product


def enrich_products_semantics(products: list[Product]) -> list[Product]:
    return [enrich_product_semantics(product) for product in products]
