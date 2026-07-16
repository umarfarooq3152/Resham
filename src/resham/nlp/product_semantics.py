"""Versioned semantic enrichment for catalog products.

This layer canonicalizes merchant metadata once at ingestion/cache load. It is
not a user-language parser: conversational semantics remain the LLM's job.
"""

import re

from resham.nlp.apparel_classification import extract_classification_request
from resham.nlp.garments import extract_garment_descriptors, unstitched_fallback_family
from resham.nlp.pakistani_events import infer_product_event
from resham.schemas.product import Product, ProductSemantics

SEMANTIC_PROFILE_VERSION = "catalog-semantic-v1"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_explicit_garment(text: str) -> str | None:
    """The first *explicitly named* garment word in `text`, or None.

    Deliberately does not fall back to fuzzy typo-correction the way
    `extract_primary_garment` does for a live shopper query — that fallback
    is only safe against free natural-language text where a near-miss
    really is a typo. Merchant `category` is often an internal collection
    code (e.g. "BTK-WEST", "Bell Bottoms", "Desi Beat") that is not prose at
    all, and those codes routinely land within one edit of an unrelated
    real garment word (`SequenceMatcher("west", "vest") == 0.75`), silently
    mislabeling hundreds of products. A missing family (left None here)
    still ranks correctly via the embedded title text in vector search;
    a wrong one actively pollutes eligibility's category filter for every
    shopper who searches that garment.
    """
    garments = extract_garment_descriptors(text)
    return garments[0] if garments else None


def enrich_product_semantics(product: Product) -> Product:
    """Attach a compact canonical profile, preserving the Product identity."""
    core_source = " ".join((
        product.name,
        product.category or "",
        " ".join(product.shopify_tags),
        " ".join(product.tags),
    ))
    # Title first: it's the merchant's own free-text description of the
    # item and the most reliable source. `category` is checked only as a
    # fallback and only for an explicit word, never fuzzy-guessed — a
    # collection bucket like "BTK-WEST" can hold both a suit and a top, so
    # no code-level correction could ever be right for the whole bucket.
    family = (
        _first_explicit_garment(product.name)
        or _first_explicit_garment(product.category or "")
        or _first_explicit_garment(" ".join(product.shopify_tags))
        # Only once no source names a specific garment anywhere: "unstitched"
        # reliably means loose fabric for a suit in this catalog, but must
        # never outrank a specific component word (see
        # unstitched_fallback_family's docstring for why order matters here).
        or unstitched_fallback_family(core_source)
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
