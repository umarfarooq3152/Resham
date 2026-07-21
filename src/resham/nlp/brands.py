"""Conservative extraction of explicitly requested catalog brands."""

import re
from collections.abc import Iterable

from resham.nlp.colors import BASE_COLORS


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def extract_requested_brands(
    query: str,
    brands: Iterable[tuple[str, str]],
) -> list[str]:
    """Return active brand slugs whose declared names occur as whole words.

    ``brands`` is ``(slug, name)`` data from the registry, rather than a
    global hard-coded vocabulary. A shopper must spell a real brand name (or
    its slug) in the message; partial/fuzzy matches are intentionally ignored
    so a product/style word cannot silently constrain the catalog.
    """
    normalized_query = _normalized(query)
    if not normalized_query:
        return []

    requested: list[str] = []
    for slug, name in brands:
        aliases = {_normalized(name), _normalized(slug)}
        if any(
            alias and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized_query)
            # A declared brand can share a retail shade name (notably
            # "Sapphire"). Treat "sapphire-blue" / "sapphire blue" as the
            # color phrase it plainly is; other exact brand mentions remain
            # a brand constraint.
            and not re.search(
                rf"(?<![a-z0-9]){re.escape(alias)}\s+(?:{'|'.join(BASE_COLORS)})(?![a-z0-9])",
                normalized_query,
            )
            for alias in aliases
        ):
            requested.append(slug)
    return requested
