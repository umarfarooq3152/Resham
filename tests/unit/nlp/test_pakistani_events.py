from resham.nlp.pakistani_events import event_match_score, extract_event
from resham.schemas.product import Product
from resham.services.search_service import SearchService


def _product(name: str, *, category: str = "", colors=None, tags=None) -> Product:
    return Product(
        id=f"test:{name}", name=name, category=category, colors=colors or [],
        tags=tags or [], description="", price=5000, image="https://example.com/a.jpg",
        product_url="https://example.com/a",
    )


def test_pakistani_event_aliases_normalize_to_canonical_names():
    cases = {
        "cousin's dholki": "mehndi",
        "outfit for my mayun": "mehndi",
        "nikkah ceremony": "nikah",
        "shaadi clothes": "baraat",
        "valima reception": "walima",
        "mangni look": "engagement",
        "14 August kurta": "independence day",
        "convocation outfit": "graduation",
        "clothes for chand raat": "chand raat",
        "post wedding family dinner": "dawat",
        "university annual dinner": "farewell",
        "school colour day": "color day",
        "school annual day": "sports day",
        "parent teacher meeting": "school function",
        "rukhsati outfit": "baraat",
        "clothes for daaku day": "daaku day",
        "outfit for dacoit day": "daaku day",
        "i want to dress like a badmaash": "daaku day",
        "gangster day at uni": "daaku day",
        "all black day tomorrow": "black day",
        "white out day": "white day",
        "glow day outfit": "neon day",
        "pyjama day at college": "pajama day",
        "hawaiian day theme": "beach day",
        "jeans day theme": "denim day",
        "peshawari day dress": "pathani day",
        "throwback day outfit": "retro day",
    }
    for query, expected in cases.items():
        assert extract_event(query) == expected


def test_office_meeting_phrasing_resolves_to_office_occasion():
    # Real bug report phrasing: "office" aliases didn't cover generic
    # meeting/business-trip language, so a shopper describing an actual
    # work trip got no occasion match at all.
    assert extract_event("i have a meeting in london next week") == "office"


def test_mehndi_accepts_colorful_festive_garment():
    product = _product(
        "Mirror Work Sharara", category="Sharara", colors=["Yellow"],
        tags=["embroidered", "traditional"],
    )
    assert event_match_score(product, "mehndi") == 1.0


def test_mehndi_rejects_plain_or_unrelated_items():
    plain_kurta = _product("Plain Kurta", category="Kurta", colors=["Grey"])
    stencil = _product("Mehndi Stencil", category="Accessories", colors=["Yellow"])
    assert event_match_score(plain_kurta, "mehndi") == 0.0
    # Literal event words alone are insufficient for a non-garment.
    assert event_match_score(stencil, "mehndi") == 0.0

    misspelled_stencil = _product(
        "HENNA STANCILS", category="Accessories", colors=["Yellow"]
    )
    assert event_match_score(misspelled_stencil, "mehndi") == 0.0


def test_mehndi_search_curates_inferred_products_without_literal_event_tag():
    festive = _product(
        "Mirror Work Sharara", category="Sharara", colors=["Yellow"],
        tags=["embroidered", "traditional"],
    )
    plain = _product("Plain Grey Kurta", category="Kurta", colors=["Grey"])
    unrelated = _product("Yellow Oxford Shirt", category="Shirt", colors=["Yellow"])

    result = SearchService.search(
        [plain, unrelated, festive], occasion="mehndi", page_size=10
    )

    assert result.items == [festive]


def test_mehndi_uses_ecommerce_formality_tags_from_guide():
    party_wear = _product(
        "Silk Sharara Set", category="Sharara", colors=["Grey"],
        tags=["Party Wear"],
    )
    daily = _product(
        "Plain Sharara Set", category="Sharara", colors=["Grey"],
        tags=["Daily Wear"],
    )

    assert event_match_score(party_wear, "mehndi") > 0
    assert event_match_score(daily, "mehndi") == 0
