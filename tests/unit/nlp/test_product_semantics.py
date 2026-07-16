"""Regression coverage for enrich_product_semantics' product_family
derivation — specifically that it never fuzzy-guesses a garment type from a
merchant's internal category code, which used to mislabel real products
(e.g. "BTK-WEST" ~ "vest") across hundreds of rows in the live catalog."""

from resham.nlp.product_semantics import enrich_product_semantics
from resham.schemas.product import Product


def _product(name: str, category: str | None, shopify_tags: list[str] | None = None) -> Product:
    return Product(
        id="brand:1",
        name=name,
        price=1000.0,
        category=category,
        shopify_tags=shopify_tags or [],
        image="https://example.com/a.jpg",
        product_url="https://example.com/a",
    )


def test_title_garment_word_wins_over_a_category_code_that_fuzzy_matches_something_else():
    """Real bug: category "BTK-WEST" ~ "vest" at edit-distance ratio 0.75,
    which used to short-circuit before the title's explicit "TOP" was ever
    checked."""
    product = _product("LEMON PRINTED TOP", category="BTK-WEST")

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "top"


def test_category_code_with_no_explicit_garment_word_does_not_produce_a_guess():
    """"Weavers Tale Set" names no real garment anywhere — family should be
    None, not a fuzzy guess like "sweater", since a wrong family actively
    pollutes eligibility's category filter for every shopper searching that
    garment (a missing family still ranks fine via embedded title text)."""
    product = _product("Weavers Tale Set", category="Weavers Tale")

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family is None


def test_bell_bottoms_category_does_not_shadow_the_actual_trouser_title():
    product = _product("Trouser Bell-bottom - Black", category="Bell Bottoms")

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "trousers"


def test_boy_short_category_does_not_produce_shirt_for_an_actual_shorts_item():
    product = _product("Shorts With Flap Pocket", category="Boy Short")

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "shorts"


def test_an_explicit_garment_word_in_category_alone_still_resolves():
    """Normal case: a category that directly names the garment (no fuzzy
    correction needed) still works exactly as before."""
    product = _product("Signature Piece - 5001", category="Kurtas")

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "kurta"


def test_falls_back_to_shopify_tags_when_title_and_category_have_no_explicit_word():
    product = _product("Signature Piece - 5001", category="Weavers Tale", shopify_tags=["Kurta"])

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "kurta"


def test_unstitched_with_no_named_component_anywhere_falls_back_to_suit():
    """"GREEN UNSTITCHED 3PC" (8,124 products in the live catalog carry this
    exact naming convention) names no specific garment word anywhere —
    "unstitched" fabric sets are conventionally a suit in this catalog, but
    only once nothing more specific was found (see the next test)."""
    product = _product("GREEN LAWN UNSTITCHED 3PC", category="Unstitched")

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "suit"


def test_unstitched_never_shadows_a_specific_named_component():
    """Real catalog pattern: "Khaddar Shirt (Unstitched)" is genuinely
    fabric for a single shirt, not a 3-piece suit — the explicit "shirt"
    must always win over the generic "unstitched" fallback, regardless of
    where "unstitched" sits in the title."""
    product = _product("Khaddar Shirt (Unstitched)", category=None)

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "shirt"


def test_unstitched_appearing_before_the_component_word_still_does_not_shadow_it():
    product = _product("Unstitched Shirt Fabric", category=None)

    enriched = enrich_product_semantics(product)

    assert enriched.semantics.product_family == "shirt"
