"""Regression coverage for three real bugs in _diversify_by_brand /
SearchService.search's total-count, all documented in the
_diversify_by_brand docstring (src/resham/services/search_service.py):

1. A brand with zero keyword matches for "lehenga" still contributed its
   top-priced item (a hand towel) into round 1 of round-robining.
2. Searching "sherwani" (a category no registered brand carries) appended
   the entire catalog as filler — surfacing socks and hair ties.
3. A real "korean pant" search with ~15 genuine matches reported
   total=4197 (the full catalog size) because non-matches were appended
   as filler after the real matches.

Cases 1 and 2 call _diversify_by_brand directly with hand-built (Product,
score) tuples, bypassing SearchService.search's category pre-filter
entirely — that gate runs before scoring and would otherwise exclude an
unrelated filler product before it ever reaches diversification, making
the test pass for the wrong reason. Case 3 goes through the full
SearchService.search() since it's about `total` staying decoupled from
the diversified list, and uses filler products that pass the category
gate (matching category="Trousers") but score 0 on keywords, so they
genuinely reach diversification.
"""

from resham.schemas.product import Product
from resham.services.search_service import SearchService, _diversify_by_brand


def _product(
    brand: str,
    external_id: str,
    name: str,
    price: float,
    category: str | None = None,
) -> Product:
    return Product(
        id=f"{brand}:{external_id}",
        name=name,
        price=price,
        category=category,
        image="https://example.com/1.jpg",
        product_url="https://example.com/products/1",
    )


def test_zero_score_brand_never_contributes_a_filler_item():
    lehenga = _product("brand-a", "1", "Embroidered Lehenga", 12000)
    towel = _product("brand-b", "1", "3 Piece Embroidered Towel Set", 7000)

    ranked = _diversify_by_brand([(lehenga, 1.0), (towel, 0.0)], limit=10)

    assert ranked == [lehenga]
    assert towel not in ranked


def test_no_relevant_matches_returns_empty_not_the_whole_catalog():
    socks = _product("brand-a", "1", "Ankle Socks", 500)
    hair_tie = _product("brand-b", "1", "Hair Tie Set", 300)

    ranked = _diversify_by_brand([(socks, 0.0), (hair_tie, 0.0)], limit=10)

    assert ranked == []


def test_free_text_total_reflects_real_matches_not_the_whole_catalog():
    matches = [
        _product(f"brand-{i}", "1", "Korean Style Wide Pant", 3000, category="Trousers")
        for i in range(3)
    ]
    # Passes the category gate (category="Trousers" matches the "pant"
    # request) but scores 0 on the "korean" keyword, so it's real filler
    # that must reach diversification and still be excluded as irrelevant.
    filler = [
        _product(f"brand-f{i}", "1", "Plain Trousers", 2000, category="Trousers")
        for i in range(15)
    ]

    result = SearchService.search(matches + filler, query="korean pant", page_size=50)

    assert result.total == len(matches)
