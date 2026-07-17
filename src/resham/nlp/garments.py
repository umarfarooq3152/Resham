"""Deterministic garment/style extraction for conversational web search."""

import re
from difflib import SequenceMatcher

from resham.nlp.colors import extract_color

_DESCRIPTOR_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("shalwar kameez", (r"\bshalwar\s+kameez(?:es)?\b", r"\bsalwar\s+kameez(?:es)?\b")),
    ("shirt dress", (r"\bshirt\s+dress(?:es)?\b",)),
    ("wrap dress", (r"\bwrap\s+dress(?:es)?\b",)),
    ("cocktail dress", (r"\bcocktail\s+dress(?:es)?\b",)),
    ("slip dress", (r"\bslip\s+dress(?:es)?\b",)),
    ("cigarette pants", (r"\bcigarette\s+pants?\b",)),
    ("peplum top", (r"\bpeplum(?:\s+tops?)?\b",)),
    ("crop top", (r"\bcrop\s+tops?\b",)),
    ("polo", (r"\bpolo\s+shirts?\b", r"\bpolos?\b")),
    ("t-shirt", (r"\bt[ -]?shirts?\b", r"\btees?\b")),
    ("tank top", (r"\btank\s+tops?\b", r"\bcamisoles?\b")),
    ("sweatshirt", (r"\bsweatshirts?\b",)),
    ("tracksuit", (r"\btrack\s*suits?\b",)),
    ("co-ord", (r"\bco[ -]?ords?(?:\s+sets?)?\b", r"\bmatching\s+sets?\b")),
    ("prince coat", (r"\bprince\s+coats?\b",)),
    ("waistcoat", (r"\bwaist\s*coats?\b",)),
    ("vest", (r"\bvests?\b", r"\bkoti\b",)),
    ("blouse", (r"\bblouses?\b",)),
    ("tunic", (r"\btunics?\b",)),
    ("kurti", (r"\bkurtis?\b",)),
    ("kurta", (r"\bkurtas?\b",)),
    ("kameez", (r"\bkameez(?:es)?\b",)),
    ("lehenga", (r"\blehengas?\b",)),
    ("sherwani", (r"\bsherwanis?\b",)),
    ("achkan", (r"\bachkans?\b",)),
    ("gharara", (r"\bghararas?\b",)),
    ("sharara", (r"\bshararas?\b",)),
    ("shalwar", (r"\b(?:shalwar|salwar)s?\b",)),
    ("pishwas", (r"\bpishwas\b",)),
    ("saree", (r"\bsar(?:ee|i)s?\b",)),
    ("abaya", (r"\babayas?\b",)),
    ("maxi", (r"\bmaxis?\b",)),
    ("gown", (r"\bgowns?\b",)),
    ("suit", (r"\b(?:2|3|two|three)[ -]?piece(?:\s+\w+){0,2}\s+suits?\b", r"\bsuits?\b")),
    ("dress", (r"\bdress(?:es)?\b",)),
    ("shirt", (r"\bshirts?\b",)),
    ("top", (r"\btops?\b",)),
    ("palazzo", (r"\bpalazzos?\b",)),
    ("leggings", (r"\bleggings?\b", r"\btights?\b")),
    ("joggers", (r"\bjoggers?\b", r"\btrack\s+pants?\b")),
    ("jeans", (r"\bjeans?\b", r"\bdenims?\b")),
    ("shorts", (r"\bshorts\b", r"\bbike\s+short\b")),
    ("skirt", (r"\bskirts?\b",)),
    ("trousers", (r"\btrousers?\b", r"\bpants?\b")),
    ("blazer", (r"\bblazers?\b",)),
    ("shrug", (r"\bshrugs?\b",)),
    ("cape", (r"\bcapes?\b",)),
    ("cardigan", (r"\bcardigans?\b",)),
    ("jacket", (r"\bjackets?\b",)),
    ("coat", (r"\bcoats?\b",)),
    ("windbreaker", (r"\bwindbreakers?\b",)),
    ("hoodie", (r"\bhoodies?\b",)),
    ("sweater", (r"\bsweaters?\b",)),
    ("jumpsuit", (r"\bjumpsuits?\b",)),
    ("sports bra", (r"\bsports?\s+bras?\b",)),
    ("underwear", (r"\b(?:underwear|briefs?|boxers?|lingerie)\b",)),
    ("socks", (r"\bsocks?\b",)),
    ("scarf", (r"\bscar(?:f|ves)\b",)),
    ("headwear", (r"\b(?:headwear|caps?|hats?|beanies?)\b",)),
    ("bag", (r"\b(?:bags?|handbags?|totes?|clutches?|cross[ -]?body)\b",)),
    ("belt", (r"\bbelts?\b",)),
    ("dupatta", (r"\bdupattas?\b",)),
    ("shawl", (r"\bshawls?\b",)),
    ("swimwear", (r"\b(?:swimwear|swimsuits?|bathing suits?)\b",)),
    ("shoes", (
        r"\bdress\s+shoes?\b",
        r"\b(?:shoes?|footwear|sneakers?|sandals?|slides?|loafers?|heels?|"
        r"flats?|khussas?|trainers?|boots?)\b",
    )),
    ("knitted", (r"\bknit(?:ted|wear)?\b",)),
    ("embroidered", (r"\bembroider(?:ed|y)\b",)),
    ("printed", (r"\b(?:printed|print)\b",)),
    ("striped", (r"\bstrip(?:e|ed|es|ing)\b",)),
    ("leather", (r"\b(?:faux|pu|genuine)?\s*leather\b",)),
    ("denim", (r"\bdenim\b",)),
    ("suede", (r"\bsuede\b",)),
    ("cotton", (r"\bcotton\b",)),
    ("linen", (r"\blinen\b",)),
    ("silk", (r"\bsilk\b",)),
    ("wool", (r"\bwool(?:len)?\b",)),
    ("velvet", (r"\bvelvet\b",)),
    ("chiffon", (r"\bchiffon\b",)),
    ("organza", (r"\borganza\b",)),
    ("satin", (r"\bsatin\b",)),
    ("khaddar", (r"\bkhaddar\b",)),
    ("lawn", (r"\blawn\b",)),
    ("oversized", (r"\bover[ -]?sized\b",)),
    ("slim fit", (r"\bslim[ -]?fits?\b",)),
    ("regular fit", (r"\bregular[ -]?fits?\b",)),
    ("relaxed fit", (r"\brelaxed[ -]?fits?\b",)),
    ("baggy", (r"\bbaggy\b",)),
    ("wide leg", (r"\bwide[ -]?legs?\b",)),
    ("straight fit", (r"\bstraight[ -]?(?:fit|leg)s?\b",)),
    ("cropped", (r"\bcropped\b",)),
    ("formal", (r"\bformal(?:wear| wear)?\b",)),
    ("casual", (r"\bcasual(?:wear| wear)?\b",)),
    ("semi-formal", (r"\bsemi[ -]?formal\b",)),
    ("party", (r"\bparty\s+wear\b",)),
    ("activewear", (r"\b(?:activewear|sportswear|gym wear|workout clothes)\b",)),
    ("eastern", (r"\beastern(?: wear)?\b",)),
    ("western", (r"\bwestern(?: wear)?\b",)),
)

# These labels materially constrain search and must never be accepted merely
# because an LLM inferred them. They are retained only when the shopper used a
# corresponding phrase in this turn (or when already persisted from an earlier
# explicitly grounded turn).
_STRICT_STYLE_LABELS = {
    "formal",
    "casual",
    "semi formal",
    "semi-formal",
    "party",
    "festive",
    "traditional",
}

_STYLE_DESCRIPTORS = {
    "knitted",
    "embroidered",
    "formal",
    "casual",
    "semi-formal",
    "party",
    "eastern",
    "western",
    "printed", "leather", "denim", "suede", "cotton", "linen", "silk",
    "wool", "velvet", "chiffon", "organza", "satin", "khaddar", "lawn",
    "oversized", "slim fit", "regular fit", "relaxed fit", "baggy",
    "wide leg", "straight fit", "cropped",
    "striped",
}

# Merchant product types often use a store-specific family label instead of
# the shopper's everyday garment word. These aliases supplement the explicit
# vocabulary above; the title/category still has to name the same product
# family, so a description mentioning "polo-style" cannot turn a camisole
# into a polo result.
_GARMENT_METADATA_ALIASES: dict[str, tuple[str, ...]] = {
    "activewear": (
        "performance", "training", "dri fit", "moisture wicking",
        "sports bra", "sports hijab", "sports abaya", "bike short",
        "yoga pant", "track pant", "running shoe",
    ),
    "shoes": ("footwear", "oxford", "derby", "pump", "chappal"),
    "sweater": ("knitwear", "pullover", "jumper"),
    "sweatshirt": ("sweat shirt",),
    "jacket": ("outerwear", "bomber", "puffer"),
    "trousers": ("bottoms", "pants"),
    "top": ("fashion top", "eastern top", "western top"),
    "co-ord": ("coord", "coord set", "co ord set"),
    "tracksuit": ("track suit", "track set"),
    "suit": ("2 piece", "3 piece", "two piece", "three piece"),
    "shalwar kameez": ("eastern suit",),
}

_GARMENT_TYPO_ALIASES = {
    "tshirt": "t-shirt",
    "polo": "polo",
    "shirt": "shirt",
    "blouse": "blouse",
    "sweater": "sweater",
    "hoodie": "hoodie",
    "jacket": "jacket",
    "sweatshirt": "sweatshirt",
    "tracksuit": "tracksuit",
    "top": "top",
    "coat": "coat",
    "vest": "vest",
    "jean": "jeans",
    "trouser": "trousers",
    "kurta": "kurta",
    "kurti": "kurti",
    "kameez": "kameez",
    "shalwar": "shalwar",
    "lehenga": "lehenga",
    "gharara": "gharara",
    "sharara": "sharara",
    "sherwani": "sherwani",
    "dress": "dress",
    "skirt": "skirt",
    "belt": "belt",
}

_STYLE_CANONICAL_ALIASES = {
    "stripe": "striped",
    "stripes": "striped",
    "striped": "striped",
}


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def extract_search_descriptors(text: str) -> list[str]:
    """Return explicitly named garments/styles, avoiding nested categories."""
    matches: list[tuple[int, int, str]] = []
    lowered = text.lower()
    # "Dress up like a bandit" uses dress as a verb; treating it as the
    # Western dress category blocks the intended daaku/kurta fallback.
    lowered = re.sub(r"\bdress(?:ed)?\s+up\b", " ", lowered)
    for descriptor, patterns in _DESCRIPTOR_PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if match:
                matches.append((match.start(), match.end(), descriptor))
                break

    # Prefer the longest phrase when patterns overlap: "polo shirt" is a polo,
    # not both a polo and a generic shirt.
    accepted: list[tuple[int, int, str]] = []
    for start, end, descriptor in sorted(matches, key=lambda item: item[1] - item[0], reverse=True):
        if any(start < used_end and end > used_start for used_start, used_end, _ in accepted):
            continue
        accepted.append((start, end, descriptor))
    return [item[2] for item in sorted(accepted)]


def extract_garment_descriptors(text: str) -> list[str]:
    """Return concrete product categories, excluding style/family labels."""
    return [
        descriptor
        for descriptor in extract_search_descriptors(text)
        if descriptor not in _STYLE_DESCRIPTORS
    ]


_UNSTITCHED_PATTERN = re.compile(r"\bunstitched\b")


def unstitched_fallback_family(text: str) -> str | None:
    """Last-resort signal only: "unstitched" reliably means loose fabric
    for a shalwar-kameez/suit in this catalog, but titles routinely name a
    single component alongside it too (e.g. "Khaddar Shirt (Unstitched)" is
    genuinely shirt fabric, not a suit). Callers must only use this after
    `extract_garment_descriptors` has already found nothing anywhere
    (title, category, tags) — that ordering is what keeps a specific named
    component from ever being shadowed by this catch-all."""
    return "suit" if _UNSTITCHED_PATTERN.search(_normalized(text)) else None


def extract_primary_garment(text: str) -> str | None:
    """Return the first explicitly requested product in conversational order."""
    garments = extract_garment_descriptors(text)
    if garments:
        return garments[0]

    best: tuple[float, int, str] | None = None
    typo_text = re.sub(r"\bdress(?:ed)?\s+up\b", " ", text.lower())
    for index, token in enumerate(re.findall(r"[a-z]+", typo_text)):
        if len(token) < 4 or extract_color(token):
            continue
        singular = token[:-1] if token.endswith("s") else token
        for alias, garment in _GARMENT_TYPO_ALIASES.items():
            ratio = SequenceMatcher(None, singular, alias).ratio()
            if ratio >= 0.75 and (best is None or ratio > best[0]):
                best = (ratio, index, garment)
    return best[2] if best else None


def without_garment_descriptors(descriptors: list[str]) -> list[str]:
    """Keep subjective refinements while removing product/audience fields."""
    result: list[str] = []
    for descriptor in descriptors:
        cleaned = _normalized(descriptor)
        while garments := extract_garment_descriptors(cleaned):
            previous = cleaned
            for garment in garments:
                cleaned = re.sub(
                    rf"\b{re.escape(_normalized(garment))}\b", " ", cleaned
                )
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned == previous:
                cleaned = ""
                break
        if cleaned in {"2 piece", "3 piece", "two piece", "three piece"}:
            cleaned = ""
        # Audience belongs in SessionState.department, never in strict style
        # keywords. A provider returning style="female" caused women's Mehndi
        # searches to require the literal word "female" on every product.
        cleaned = re.sub(
            r"\b(?:women(?: s)?|womens?|woman(?: s)?|ladies|female|"
            r"men(?: s)?|mens?|man(?: s)?|gents|male|girls?|boys?)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = _STYLE_CANONICAL_ALIASES.get(cleaned, cleaned)
        if cleaned and cleaned not in {item.lower() for item in result}:
            result.append(cleaned)
    return result


# Verified against the live catalog (see product_semantics.py's
# product_tradition derivation): only families that are unambiguously one
# tradition in this catalog's real usage are listed. Genuinely mixed
# families are deliberately omitted rather than guessed — e.g. "shirt"
# (18k+ products) is a near-even split between eastern kameez tops
# ("Stitched Embroidered Lawn Shirt+ Shalwar") and western casual shirts
# ("Baggy Fit Checkered Shirt"), so it stays untagged rather than risk
# hard-excluding real matches on either side of a tradition-filtered search.
_EASTERN_FAMILIES = frozenset({
    "kurta", "kurti", "shalwar kameez", "kameez", "shalwar", "lehenga",
    "sherwani", "achkan", "gharara", "sharara", "saree", "abaya", "pishwas",
    "prince coat", "vest", "suit",
})
_WESTERN_FAMILIES = frozenset({
    "jeans", "t-shirt", "polo", "tank top", "sweatshirt", "tracksuit",
    "hoodie", "blazer", "joggers", "jumpsuit", "cocktail dress", "wrap dress",
    "shirt dress", "slip dress", "gown", "crop top", "peplum top",
    "cigarette pants", "windbreaker", "sports bra", "cardigan", "sweater",
    "coat", "leggings", "skirt", "dress", "shorts", "swimwear", "jacket",
    "maxi", "trousers", "activewear",
})


def tradition_from_family(product_family: str | None) -> str | None:
    """Derive eastern/western from the already-cleaned `product_family`
    signal instead of a free-text heuristic — a hand-rolled classifier
    matching fabric/construction words is what previously misclassified
    real products (e.g. "collar" incidentally matching inside "Johnny
    Collar Polo" and bumping it to "formal"). Ambiguous families return
    None rather than a guess; ranking treats a missing tradition as no
    boost, never as a mismatch."""
    if product_family in _EASTERN_FAMILIES:
        return "eastern"
    if product_family in _WESTERN_FAMILIES:
        return "western"
    return None


def is_recognized_garment_family(product_family: str | None) -> bool:
    """True only for families this catalog has verified are actual
    clothing (see `tradition_from_family`'s curated lists) — gates
    `apparel_classification.classify_apparel_text`'s formality/tradition
    fallback so a non-garment product (bag, scarf, dupatta, accessory)
    never gets a guessed formality tier the heuristic was never designed
    to produce for it."""
    return product_family in _EASTERN_FAMILIES or product_family in _WESTERN_FAMILIES


def requested_tradition(style_descriptors: list[str]) -> str | None:
    """Pull an eastern/western/fusion request out of the turn's style
    descriptors, for threading into search/ranking.py's soft tradition
    boost."""
    lowered = {item.lower().strip() for item in style_descriptors}
    if "eastern" in lowered:
        return "eastern"
    if "western" in lowered:
        return "western"
    if "fusion" in lowered:
        return "fusion"
    return None


_REQUESTABLE_FORMALITY = {"formal", "casual", "semi-formal", "party", "bridal"}


def requested_formality(style_descriptors: list[str]) -> str | None:
    """Pull an explicit formality request out of the turn's style
    descriptors, for threading into search/ranking.py's soft formality
    boost."""
    for item in style_descriptors:
        key = item.lower().strip()
        if key in _REQUESTABLE_FORMALITY:
            return key
    return None


def matches_garment_text(value: str, garment: str | None) -> bool:
    """Match a product title/type/tag string to one canonical garment family."""
    if not garment:
        return True
    canonical = _normalized(garment)
    normalized = _normalized(value)
    aliases = (canonical, *_GARMENT_METADATA_ALIASES.get(canonical, ()))
    return any(
        re.search(rf"\b{re.escape(_normalized(alias))}s?\b", normalized)
        for alias in aliases
    )


def ground_style_descriptors(text: str, provider_descriptors: list[str]) -> list[str]:
    """Remove inferred hard styles and add explicit deterministic descriptors."""
    explicit = extract_search_descriptors(text)
    explicit_keys = {item.lower() for item in explicit}
    grounded = []
    for item in provider_descriptors:
        key = item.lower().strip()
        inferred_garments = extract_garment_descriptors(item)
        if key in _STRICT_STYLE_LABELS and key not in explicit_keys:
            continue
        if inferred_garments and not any(
            garment.lower() in explicit_keys for garment in inferred_garments
        ):
            continue
        grounded.append(item)
    for item in explicit:
        if item.lower() not in {existing.lower().strip() for existing in grounded}:
            grounded.append(item)
    return grounded
