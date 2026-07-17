"""Versioned semantic enrichment for catalog products.

This layer canonicalizes merchant metadata once at ingestion/cache load. It is
not a user-language parser: conversational semantics remain the LLM's job.
"""

import re

from resham.nlp.apparel_classification import (
    BRIDAL,
    CASUAL,
    FORMAL,
    PARTY,
    SEMI_FORMAL,
    classify_product,
    extract_classification_request,
)
from resham.nlp.colors import extract_color
from resham.nlp.garments import (
    extract_garment_descriptors,
    is_recognized_garment_family,
    tradition_from_family,
    unstitched_fallback_family,
)
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
    # A fallback signal only: eligibility.py uses this exclusively when a
    # variant's own merchant-set color is missing entirely (~57% of
    # in-stock products in the live catalog have no usable variant color
    # at all — they're otherwise unreachable by any color-filtered
    # search). Reads the same title/tags plus the description, since this
    # catalog's descriptions routinely carry an explicit "Color: X" line
    # that title/tags alone miss — verified live: combining description
    # roughly quadrupled how many of those products became recoverable
    # (20% -> 72% in a random sample) with no observed false positives,
    # unlike a generic marketing blurb this catalog's descriptions are
    # short, structured, per-product fabric/color specs.
    text_derived_color = extract_color(
        f"{product.name} {' '.join(product.shopify_tags)} {product.description or ''}"
    )
    classification = extract_classification_request(core_source)
    # `classification.tradition`/`.formality` only fire on a literal word
    # ("eastern", "formal wear", ...) in the title/tags, which is rare —
    # real coverage comes from two richer, still-conservative fallbacks
    # below: `tradition_from_family` (a curated lookup over the verified
    # `family` signal) and `classify_apparel_text` (item + fabric +
    # construction rules, gated to families already confirmed to be real
    # clothing via `is_recognized_garment_family` — its formality tier
    # always resolves to *something*, defaulting to semi-formal absent any
    # signal, which is meaningless for a non-garment product like a bag).
    apparel_tier = classify_product(product)
    product_tradition = (
        classification.tradition
        or tradition_from_family(family)
        # "shirt" is deliberately excluded from tradition_from_family (see
        # its docstring) because it's a near-even eastern/western split in
        # this catalog — but classify_apparel_text's WESTERN_ITEMS also
        # lists a bare "shirt", which would silently reintroduce that same
        # guess. Every other unrecognized family has no such documented
        # ambiguity, so it's a fair fallback target.
        or (apparel_tier.tradition if family != "shirt" else None)
    )
    product_formality = classification.formality
    if product_formality is None and is_recognized_garment_family(family):
        product_formality = {
            CASUAL: "casual",
            SEMI_FORMAL: "semi-formal",
            FORMAL: "formal",
            PARTY: "party",
            BRIDAL: "bridal",
        }[apparel_tier.formality]
    attributes = list(dict.fromkeys(filter(None, (
        *product.tags,
        *extract_garment_descriptors(core_source),
        product_formality,
        product_tradition,
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
        text_derived_color=text_derived_color,
        product_tradition=product_tradition,
        product_formality=product_formality,
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
