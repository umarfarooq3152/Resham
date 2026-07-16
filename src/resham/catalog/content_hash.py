"""Content hashing for incremental re-embedding.

Hashes ONLY the text fields that feed the Chroma document (title,
description, category, occasion, colors, tags, shopify_tags) — deliberately
excluding price/availability so a price change or stock flip never triggers
an expensive re-embed. The indexer re-embeds a product only when this hash
changes from what's stored in `products.content_hash`.
"""

import hashlib

from resham.catalog.mapper import MappedProduct


def compute_content_hash(product: MappedProduct, occasion: str | None, tags: list[str]) -> str:
    """Stable hash over the embedding-relevant fields of a mapped product.

    `occasion`/`tags` are passed in separately because they're derived by
    the NLP tagging layer (keyword_matcher/pakistani_events) after mapping,
    not present on `MappedProduct` itself.
    """
    parts = [
        product.title.strip().lower(),
        (product.description_text or "").strip().lower(),
        (product.category or "").strip().lower(),
        (occasion or "").strip().lower(),
        ",".join(sorted(c.lower() for c in product.colors)),
        ",".join(sorted(t.lower() for t in tags)),
        ",".join(sorted(t.lower() for t in product.shopify_tags)),
    ]
    digest_input = "|".join(parts).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()
