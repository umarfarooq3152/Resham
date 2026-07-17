"""Map raw Shopify product JSON into a durable, variant-aware intermediate
representation for the catalog repository to upsert into Postgres.

Reuses Dhaaga's proven filtering/tagging heuristics (app/shopify/mapper.py)
almost verbatim, but — unlike that mapper, which collapses a product to a
single price and a union of colors/sizes — this one preserves per-variant
color+size+price+availability coexistence, since eligibility filtering
(search/eligibility.py) requires a single available variant to satisfy
color, size, and price simultaneously.

Also unlike the live mapper, a product that is currently fully out of stock
is NOT dropped: it's mapped with `in_stock=False` so the durable catalog
keeps a record of it (and it can come back into stock on a later crawl).
Only permanent category exclusions (non-apparel, unit-sale, implausible
price, no image at all) are still hard-dropped at ingestion.
"""

import logging
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any

from resham.nlp.kids_age import extract_age_ranges

logger = logging.getLogger(__name__)


def _contains_word(keyword: str, text: str) -> bool:
    """Whole-word match, tolerant of a simple trailing plural "s" — plain
    substring matching lets single-word keywords like "boy" match inside
    unrelated words (e.g. "boyfriend", a legitimate unisex jeans-fit term),
    but strict `\\bword\\b` matching then misses real plural product
    listings (e.g. keyword "fragrance" not matching category "Fragrances").
    """
    return re.search(rf"\b{re.escape(keyword)}s?\b", text) is not None


# Some brands (e.g. Nishat Linen's "Freedom to Buy" line) list raw fabric
# sold by the meter as regular catalog products, using a per-unit pricing
# scheme that produces nonsensical near-zero prices (e.g. Rs. 9.20) for
# what Shopify's own storefront shows as a much larger real price. These
# aren't finished garments and don't belong in an outfit-discovery catalog
# at all, so they're excluded at ingestion rather than mis-priced.
UNIT_SALE_PRODUCT_TYPES = {"meter", "meters", "yard", "yards"}
MIN_PLAUSIBLE_PRICE = 200.0  # backstop against other brands' similar data quirks

# Many Pakistani fashion brands' Shopify stores also sell non-garment
# merchandise (home textiles, fragrances, jewelry, stationery) in the same
# catalog. A shopper searching "wedding lehenga" getting a pillow cover back
# is a real, observed relevance bug. Checked against both product_type AND
# title, since several of these have no product_type set.
NON_APPAREL_KEYWORDS = [
    "pillow", "cushion", "bed sheet", "bedsheet", "quilt", "blanket", "curtain",
    "rug", "showpiece", "vase", "tray", "coaster", "candle", "home decor",
    "towel", "bath sheet", "bathrobe", "table linen",
    "perfume", "fragrance", "cologne", "eau de",
    "bangle", "bracelet", "necklace", "earring", "jewelry", "jewellery", "ring set",
    "notebook", "diary", "journal", "sunglasses", "fashion glasses",
    "mehndi stencil", "henna stencil", "stencil",
    "wallet", "potli", "mug", "kitchen", "bbq", "eye mask", "sleep mask",
]

# Footwear stays outside the main clothing-only catalog by default, but
# store-scoped search (the extension) must be able to return real shoe
# inventory when the shopper asks for it.
FOOTWEAR_KEYWORDS = [
    "shoes", "sneakers", "sandals", "slides", "chappal", "footwear",
    "heels", "flats", "loafers", "boots", "flip flop", "flip-flop",
]


def _keyword_union_pattern(keywords: list[str]) -> re.Pattern[str]:
    alternatives = "|".join(
        rf"(?:{re.escape(keyword)})s?" for keyword in sorted(keywords, key=len, reverse=True)
    )
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])")


_NON_APPAREL_PATTERN = _keyword_union_pattern(NON_APPAREL_KEYWORDS)
_NON_APPAREL_AND_FOOTWEAR_PATTERN = _keyword_union_pattern(
    [*NON_APPAREL_KEYWORDS, *FOOTWEAR_KEYWORDS]
)

# Identifies kids apparel so it can be tagged (is_kids) rather than shown
# mixed into ordinary adult searches.
KIDS_KEYWORDS = [
    "kids", "kid", "boys", "girls", "boy", "girl", "toddler", "infant",
    "newborn", "junior", "juniors",
]
KIDS_CATEGORY_PREFIXES = ("btk",)

WOMEN_AUDIENCE_WORDS = ["women", "woman", "womens", "ladies", "female"]
MEN_AUDIENCE_WORDS = ["men", "man", "mens", "male", "gents"]
UNISEX_AUDIENCE_WORDS = ["unisex", "gender neutral", "gender-neutral"]


@dataclass
class MappedVariant:
    external_variant_id: str
    color: str | None
    size: str | None
    extra_options: dict[str, str]
    price: float
    compare_at_price: float | None
    available: bool
    image_url: str | None
    sku: str | None


@dataclass
class MappedProduct:
    """Durable, variant-aware normalization of one raw Shopify product."""

    external_id: str
    handle: str | None
    title: str
    description_html: str
    description_text: str
    category: str | None
    vendor: str | None
    shopify_tags: list[str]
    is_kids: bool
    department: str | None
    age_ranges_months: list[tuple[int, int]]
    primary_image_url: str
    secondary_image_url: str | None
    product_url: str
    variants: list[MappedVariant]
    raw_shopify_json: dict[str, Any]
    colors: list[str] = field(default_factory=list)
    sizes: list[str] = field(default_factory=list)
    color_images: dict[str, str] = field(default_factory=dict)
    min_price: float = 0.0
    max_price: float = 0.0
    currency: str = "PKR"
    in_stock: bool = False


def html_to_plain_text(raw_html: str) -> str:
    """Convert merchant HTML to readable, safe plain text.

    Shopify descriptions frequently contain nested lists and editor-only
    attributes. Preserve block boundaries, remove scripts and tags, decode
    entities, and normalize whitespace at ingestion instead of at render time.
    """
    if not raw_html:
        return ""
    without_unsafe_blocks = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>", " ", raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    with_breaks = re.sub(
        r"<br\s*/?>|</(?:p|li|div|h[1-6]|tr|ul|ol)\s*>",
        "\n",
        without_unsafe_blocks,
        flags=re.IGNORECASE,
    )
    text = unescape(re.sub(r"<[^>]+>", " ", with_breaks))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_shopify_tags(shopify_product: dict[str, Any]) -> list[str]:
    """Shopify returns `tags` as either a list or a single comma-separated
    string depending on the store/API version — normalize to a list."""
    raw = shopify_product.get("tags") or []
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return [str(t).strip() for t in raw if str(t).strip()]


def is_non_apparel_listing(
    title: str,
    category: str | None,
    shopify_tags: list[str],
    *,
    allow_footwear: bool = False,
) -> bool:
    text = f"{title} {category or ''} {' '.join(shopify_tags)}".lower()
    pattern = _NON_APPAREL_PATTERN if allow_footwear else _NON_APPAREL_AND_FOOTWEAR_PATTERN
    return pattern.search(text) is not None


def is_kids_apparel(
    title: str,
    category: str | None,
    shopify_tags: list[str],
    vendor: str | None = None,
    description_text: str | None = None,
) -> bool:
    category_lower = (category or "").lower()
    if category_lower.startswith(KIDS_CATEGORY_PREFIXES) or category_lower == "kids":
        return True
    # description_text is included because this catalog's kids listings
    # sometimes name the audience only there (e.g. "toddler girls", "5 to 6
    # years") with no kids word in title/category/tags at all.
    text = (
        f"{title} {category_lower} {' '.join(shopify_tags)} {vendor or ''} "
        f"{description_text or ''}"
    ).lower()
    return any(_contains_word(keyword, text) for keyword in KIDS_KEYWORDS)


def product_department(
    title: str, category: str | None, shopify_tags: list[str], vendor: str | None
) -> str | None:
    text = f"{title} {category or ''} {' '.join(shopify_tags)} {vendor or ''}".lower()
    if any(_contains_word(word, text) for word in UNISEX_AUDIENCE_WORDS):
        return "unisex"
    women = any(_contains_word(word, text) for word in WOMEN_AUDIENCE_WORDS)
    men = any(_contains_word(word, text) for word in MEN_AUDIENCE_WORDS)
    if women and not men:
        return "women"
    if men and not women:
        return "men"
    return None


def extract_colors(shopify_product: dict[str, Any]) -> list[str]:
    """Extract unique colors from Shopify product options, falling back to
    a variant-title heuristic only when no explicit Color option exists."""
    colors = set()
    for option in shopify_product.get("options", []):
        if option.get("name", "").lower() == "color":
            colors.update(option.get("values", []))

    if not colors:
        for variant in shopify_product.get("variants", []):
            title = variant.get("title", "")
            if "/" in title:
                potential_color = title.split("/")[0].strip()
                if potential_color and len(potential_color) < 30:
                    colors.add(potential_color)

    return sorted(colors) if colors else ["Default"]


def extract_sizes(shopify_product: dict[str, Any]) -> list[str]:
    """Extract unique sizes from Shopify product options, falling back to
    a variant-title heuristic only when no explicit Size option exists."""
    sizes = set()
    for option in shopify_product.get("options", []):
        if _contains_word("size", option.get("name", "").lower()):
            sizes.update(option.get("values", []))

    if not sizes:
        for variant in shopify_product.get("variants", []):
            title = variant.get("title", "")
            if "/" in title:
                parts = title.split("/")
                if len(parts) > 1:
                    potential_size = parts[-1].strip()
                    if potential_size and len(potential_size) < 20:
                        sizes.add(potential_size)

    return sorted(sizes) if sizes else ["One Size"]


def extract_color_images(shopify_product: dict[str, Any]) -> dict[str, str]:
    """Map color option values to variant images when Shopify provides them."""
    color_option_index = None
    for index, option in enumerate(shopify_product.get("options", []), start=1):
        if option.get("name", "").lower() in {"color", "colour"}:
            color_option_index = index
            break
    if color_option_index is None:
        return {}

    images_by_id = {
        str(image.get("id")): image.get("src", "")
        for image in shopify_product.get("images", [])
        if image.get("id") and image.get("src")
    }
    images_by_variant_id = {
        str(variant_id): image.get("src", "")
        for image in shopify_product.get("images", [])
        if image.get("src")
        for variant_id in (image.get("variant_ids") or [])
    }
    result: dict[str, str] = {}
    for variant in shopify_product.get("variants", []):
        color = str(variant.get(f"option{color_option_index}") or "").strip().lower()
        featured = variant.get("featured_image") or {}
        src = featured.get("src") if isinstance(featured, dict) else None
        src = src or images_by_id.get(str(variant.get("image_id")))
        src = src or images_by_variant_id.get(str(variant.get("id")))
        if color and src and color not in result:
            result[color] = src
    return result


def extract_images(shopify_product: dict[str, Any]) -> tuple[str, str | None]:
    """Extract primary and secondary product images."""
    images = shopify_product.get("images", [])
    primary = None
    secondary = None
    if images:
        primary = images[0].get("src", "")
        if len(images) > 1:
            secondary = images[1].get("src", "")
    return primary or "", secondary


def _extract_variants(
    shopify_product: dict[str, Any], color_option_index: int | None, size_option_index: int | None
) -> list[MappedVariant]:
    variants: list[MappedVariant] = []
    for variant in shopify_product.get("variants", []):
        try:
            price = float(variant.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        compare_at_raw = variant.get("compare_at_price")
        try:
            compare_at_price = float(compare_at_raw) if compare_at_raw else None
        except (TypeError, ValueError):
            compare_at_price = None

        color = (
            str(variant.get(f"option{color_option_index}") or "").strip() or None
            if color_option_index
            else None
        )
        size = (
            str(variant.get(f"option{size_option_index}") or "").strip() or None
            if size_option_index
            else None
        )

        featured = variant.get("featured_image") or {}
        image_url = featured.get("src") if isinstance(featured, dict) else None

        variants.append(
            MappedVariant(
                external_variant_id=str(variant.get("id", "")),
                color=color,
                size=size,
                extra_options={},
                price=price,
                compare_at_price=compare_at_price,
                available=bool(variant.get("available", True)),
                image_url=image_url,
                sku=variant.get("sku") or None,
            )
        )
    return variants


def _option_indexes(shopify_product: dict[str, Any]) -> tuple[int | None, int | None]:
    color_index = None
    size_index = None
    for index, option in enumerate(shopify_product.get("options", []), start=1):
        name = option.get("name", "").lower()
        if name in {"color", "colour"} and color_index is None:
            color_index = index
        elif _contains_word("size", name) and size_index is None:
            size_index = index
    return color_index, size_index


def map_shopify_product(
    shopify_product: dict[str, Any],
    *,
    allow_footwear: bool = False,
) -> MappedProduct | None:
    """Convert raw Shopify product JSON into a durable, variant-aware record.

    Returns None for permanent category exclusions (non-apparel, unit-sale,
    implausible price, no image, missing id/title) — these never belong in
    the catalog regardless of stock state. A currently-out-of-stock product
    is still mapped (in_stock=False), not dropped, so it can be tracked and
    come back into results if it restocks on a later crawl.
    """
    try:
        external_id = str(shopify_product.get("id", ""))
        title = (shopify_product.get("title") or "").strip()
        description_html = shopify_product.get("body_html") or ""
        description_text = html_to_plain_text(description_html)
        handle = shopify_product.get("handle") or None
        category = (shopify_product.get("product_type") or "").strip() or None
        vendor = (shopify_product.get("vendor") or "").strip() or None
        shopify_tags = _extract_shopify_tags(shopify_product)

        if not external_id or not title:
            logger.warning("Skipping product: missing id or title in %s", shopify_product)
            return None

        if category and category.lower() in UNIT_SALE_PRODUCT_TYPES:
            logger.debug("Skipping unit-sale product (sold by %s): %s", category, title)
            return None

        if is_non_apparel_listing(title, category, shopify_tags, allow_footwear=allow_footwear):
            logger.debug("Skipping non-apparel product: %s (%s)", title, category)
            return None

        raw_variants = shopify_product.get("variants", [])
        prices = [float(v.get("price") or 0) for v in raw_variants if v.get("price")]
        max_observed_price = max(prices) if prices else 0.0
        if max_observed_price < MIN_PLAUSIBLE_PRICE:
            logger.debug("Skipping implausibly-priced product (Rs. %s): %s", max_observed_price, title)
            return None

        primary_image, secondary_image = extract_images(shopify_product)
        if not primary_image:
            logger.debug("Skipping product with no image: %s", title)
            return None

        is_kids = is_kids_apparel(title, category, shopify_tags, vendor, description_text)
        department = product_department(title, category, shopify_tags, vendor)
        colors = extract_colors(shopify_product)
        sizes = extract_sizes(shopify_product)
        color_images = extract_color_images(shopify_product)
        age_ranges_months = (
            extract_age_ranges([*sizes, *shopify_tags, title, category or "", vendor or ""])
            if is_kids
            else []
        )

        color_index, size_index = _option_indexes(shopify_product)
        variants = _extract_variants(shopify_product, color_index, size_index)

        available_prices = [v.price for v in variants if v.available and v.price > 0]
        all_prices = [v.price for v in variants if v.price > 0] or [max_observed_price]
        price_pool = available_prices or all_prices
        in_stock = any(v.available for v in variants)

        domain = shopify_product.get("_resham_domain", "")
        product_url = f"https://{domain}/products/{handle}" if handle and domain else ""

        return MappedProduct(
            external_id=external_id,
            handle=handle,
            title=title,
            description_html=description_html,
            description_text=description_text,
            category=category,
            vendor=vendor,
            shopify_tags=shopify_tags,
            is_kids=is_kids,
            department=department,
            age_ranges_months=age_ranges_months,
            primary_image_url=primary_image,
            secondary_image_url=secondary_image,
            product_url=product_url,
            variants=variants,
            raw_shopify_json=shopify_product,
            colors=colors,
            sizes=sizes,
            color_images=color_images,
            min_price=min(price_pool) if price_pool else 0.0,
            max_price=max(price_pool) if price_pool else 0.0,
            in_stock=in_stock,
        )
    except Exception:
        logger.exception("Failed to map Shopify product")
        return None


def map_shopify_batch(
    shopify_products: list[dict[str, Any]], domain: str
) -> list[MappedProduct]:
    """Map a batch of raw Shopify product dicts, tagging each with its
    source domain (used to build product_url) before mapping."""
    mapped: list[MappedProduct] = []
    for raw in shopify_products:
        raw_with_domain = {**raw, "_resham_domain": domain}
        product = map_shopify_product(raw_with_domain)
        if product:
            mapped.append(product)

    logger.info("Mapped %d/%d Shopify products", len(mapped), len(shopify_products))
    return mapped
