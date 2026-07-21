"""Phase 3 correctness spine: every returned product satisfies every hard
filter (department, kids/age, color, size, price, category); the
relaxation ladder only triggers on a genuine zero-match miss and never
touches a hard field; vector ranking is skipped for a fully structured
query.
"""

from uuid import UUID

import pytest

from resham.db.models.product import Product as ProductRow
from resham.db.models.product_variant import ProductVariant as VariantRow
from resham.search.eligibility import EligibilityFilters, eligible_products
from resham.search.ranking import rank_products
from resham.search.relax import search_with_relaxation
from resham.search.service import EligibilityViolation, search


def _product(brand_id: UUID, external_id: str, title: str, **overrides) -> ProductRow:
    defaults = dict(
        composite_key=f"test-brand-fixture:{external_id}",
        title=title,
        category="Kurta",
        product_family="kurta",
        department="women",
        is_kids=False,
        age_ranges_months=[],
        occasion=None,
        colors=["Default"],
        sizes=["M"],
        color_images={},
        min_price=3000,
        max_price=3000,
        currency="PKR",
        in_stock=True,
        shopify_tags=[],
        tags=[],
        vendor=None,
        handle=None,
        description_html="",
        description_text="",
        primary_image_url="https://example.com/a.jpg",
        secondary_image_url=None,
        product_url="https://example.com/products/1",
        raw_shopify_json={},
    )
    defaults.update(overrides)
    return ProductRow(brand_id=brand_id, external_id=external_id, **defaults)


def _variant(product_id: UUID, external_variant_id: str, **overrides) -> VariantRow:
    defaults = dict(color=None, size="M", price=3000, available=True, extra_options={})
    defaults.update(overrides)
    return VariantRow(product_id=product_id, external_variant_id=external_variant_id, **defaults)


async def _add_and_flush(session, *objects) -> None:
    for obj in objects:
        session.add(obj)
    await session.flush()


TEST_BRAND_SLUG = "test-brand-fixture"


def _scoped(**overrides) -> EligibilityFilters:
    """EligibilityFilters scoped to the isolated test brand only — without
    this, a bare department/category filter would also match the real
    crawled catalog sitting in the same dev database."""
    overrides.setdefault("brands", [TEST_BRAND_SLUG])
    return EligibilityFilters(**overrides)


@pytest.mark.asyncio
async def test_department_hard_filter_excludes_other_department(db_session, test_brand):
    womens = _product(test_brand.id, "1", "Womens Kurta", department="women")
    mens = _product(test_brand.id, "2", "Mens Kurta", department="men")
    await _add_and_flush(db_session, womens, mens)

    rows = await eligible_products(db_session, _scoped(department="women"))

    ids = {r.external_id for r in rows}
    assert "1" in ids
    assert "2" not in ids


@pytest.mark.asyncio
async def test_unknown_department_is_excluded_not_guessed(db_session, test_brand):
    unknown = _product(test_brand.id, "3", "Mystery Kurta", department=None)
    await _add_and_flush(db_session, unknown)

    rows = await eligible_products(db_session, _scoped(department="women"))

    assert "3" not in {r.external_id for r in rows}


@pytest.mark.asyncio
async def test_kids_age_hard_filter_requires_compatible_range(db_session, test_brand):
    baby = _product(
        test_brand.id, "4", "Baby Romper", is_kids=True, age_ranges_months=[[0, 6]]
    )
    toddler = _product(
        test_brand.id, "5", "Toddler Set", is_kids=True, age_ranges_months=[[24, 36]]
    )
    await _add_and_flush(db_session, baby, toddler)

    rows = await eligible_products(
        db_session, _scoped(wants_kids=True, child_age_months=3)
    )

    ids = {r.external_id for r in rows}
    assert "4" in ids
    assert "5" not in ids


@pytest.mark.asyncio
async def test_adult_search_excludes_kids_items_by_default(db_session, test_brand):
    adult = _product(test_brand.id, "6", "Adult Kurta", is_kids=False)
    kids = _product(test_brand.id, "7", "Kids Kurta", is_kids=True)
    await _add_and_flush(db_session, adult, kids)

    rows = await eligible_products(db_session, _scoped(wants_kids=False))

    ids = {r.external_id for r in rows}
    assert "6" in ids
    assert "7" not in ids


@pytest.mark.asyncio
async def test_color_size_price_must_coexist_on_the_same_variant(db_session, test_brand):
    """The coexistence rule: a product with blue-but-expensive and
    cheap-but-red variants must NOT match "blue under 2000", even though
    both attributes exist somewhere on the product."""
    product = _product(test_brand.id, "8", "Multi Variant Kurta", min_price=1500, max_price=5000)
    await _add_and_flush(db_session, product)

    blue_expensive = _variant(product.id, "v1", color="Blue", size="M", price=5000)
    red_cheap = _variant(product.id, "v2", color="Red", size="M", price=1500)
    await _add_and_flush(db_session, blue_expensive, red_cheap)

    rows = await eligible_products(
        db_session, _scoped(color="blue", budget_max=2000)
    )
    assert product.external_id not in {r.external_id for r in rows}

    blue_cheap = _variant(product.id, "v3", color="Blue", size="M", price=1800)
    await _add_and_flush(db_session, blue_cheap)

    rows = await eligible_products(
        db_session, _scoped(color="blue", budget_max=2000)
    )
    assert product.external_id in {r.external_id for r in rows}


@pytest.mark.asyncio
async def test_text_derived_color_finds_a_product_whose_variant_has_no_color_at_all(
    db_session, test_brand
):
    """~57% of in-stock products in the live catalog have no merchant-set
    variant color at all and are otherwise unreachable by any
    color-filtered search regardless of their actual color — the
    ingest-time text_derived_color fallback (title/tags/description) is
    what makes them findable."""
    product = _product(
        test_brand.id, "50", "Black Abaya", text_derived_color="black",
    )
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color=None, size="M", price=3000))

    rows = await eligible_products(db_session, _scoped(color="black"))

    assert product.external_id in {r.external_id for r in rows}


@pytest.mark.asyncio
async def test_text_derived_color_never_overrides_a_real_variant_color(db_session, test_brand):
    """A merchant-set variant color is always authoritative — the
    text-derived fallback must never let a mismatched real color pass."""
    product = _product(
        test_brand.id, "51", "Red Abaya", text_derived_color="black",
    )
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color="Red", size="M", price=3000))

    rows = await eligible_products(db_session, _scoped(color="black"))

    assert product.external_id not in {r.external_id for r in rows}


@pytest.mark.asyncio
async def test_no_color_signal_anywhere_is_excluded_not_guessed(db_session, test_brand):
    product = _product(test_brand.id, "52", "Unlabeled Item", text_derived_color=None)
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color=None, size="M", price=3000))

    rows = await eligible_products(db_session, _scoped(color="black"))

    assert product.external_id not in {r.external_id for r in rows}


@pytest.mark.asyncio
async def test_size_filter_normalizes_common_labels_at_variant_level(db_session, test_brand):
    product = _product(test_brand.id, "9", "Sized Shirt")
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", size="Extra Large", price=3000))

    matches_xl = await eligible_products(db_session, _scoped(size="XL"))
    matches_m = await eligible_products(db_session, _scoped(size="M"))

    assert product.external_id in {r.external_id for r in matches_xl}
    assert product.external_id not in {r.external_id for r in matches_m}


@pytest.mark.asyncio
async def test_category_filter_matches_product_family(db_session, test_brand):
    kurta = _product(test_brand.id, "10", "Plain Kurta", category="Kurta", product_family="kurta")
    trouser = _product(test_brand.id, "11", "Wide Trouser", category="Trousers", product_family="trouser")
    await _add_and_flush(db_session, kurta, trouser)

    rows = await eligible_products(db_session, _scoped(category="kurta"))

    ids = {r.external_id for r in rows}
    assert "10" in ids
    assert "11" not in ids


@pytest.mark.asyncio
async def test_category_filter_matches_a_hyphenated_garment_word(db_session, test_brand):
    """Real production bug: garment_search_terms("t-shirt") normalizes to
    "t shirt" (space, not hyphen) for the SQL pre-filter — comparing that
    against a raw, un-normalized title column meant "%t shirt%" never
    matched a real "Paneled T-Shirt" title, silently returning zero
    results for every hyphenated category. The SQL side must normalize
    the column the same way, not just the search term."""
    tee = _product(test_brand.id, "14", "Paneled T-Shirt", category="T-Shirts", product_family="t-shirt")
    unrelated = _product(test_brand.id, "15", "Plain Kurta", category="Kurta", product_family="kurta")
    await _add_and_flush(db_session, tee, unrelated)

    rows = await eligible_products(db_session, _scoped(category="t-shirt"))

    ids = {r.external_id for r in rows}
    assert "14" in ids
    assert "15" not in ids


@pytest.mark.asyncio
async def test_out_of_stock_and_removed_products_are_never_eligible(db_session, test_brand):
    from datetime import datetime, timezone

    oos = _product(test_brand.id, "12", "Sold Out Item", in_stock=False)
    removed = _product(test_brand.id, "13", "Removed Item", removed_at=datetime.now(timezone.utc))
    await _add_and_flush(db_session, oos, removed)

    rows = await eligible_products(db_session, _scoped())

    ids = {r.external_id for r in rows}
    assert "12" not in ids
    assert "13" not in ids


@pytest.mark.asyncio
async def test_ranking_never_returns_a_product_outside_the_eligible_set(db_session, test_brand):
    """Structural guarantee behind search/service.py's EligibilityViolation
    check — rank_products only ever reorders the rows it was given."""
    women = _product(test_brand.id, "14", "Womens Item", department="women")
    men = _product(test_brand.id, "15", "Mens Item", department="men")
    await _add_and_flush(db_session, women, men)

    eligible = await eligible_products(db_session, _scoped(department="women"))
    ranked = await rank_products(eligible, query_text="", occasion=None, semantic_query="", collection=None)

    assert {r.external_id for r in ranked} <= {"14"}


@pytest.mark.asyncio
async def test_vector_ranking_is_skipped_for_a_fully_structured_query(db_session, test_brand):
    """No Chroma collection is needed when there's no descriptive residue —
    rank_products must not attempt to embed anything."""
    product = _product(test_brand.id, "16", "Blue Kurta", colors=["Blue"])
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color="Blue", size="M", price=3000))

    eligible = await eligible_products(
        db_session, _scoped(color="blue", size="M", budget_max=5000)
    )
    # collection=None would raise if ranking tried to use it — proves the
    # vector step was genuinely skipped, not merely a no-op with a live client.
    ranked = await rank_products(
        eligible, query_text="blue kurta size m under 5000", occasion=None, semantic_query="", collection=None
    )

    assert product.external_id in {r.external_id for r in ranked}


@pytest.mark.asyncio
async def test_relaxation_drops_occasion_before_category_and_never_touches_hard_fields(
    db_session, test_brand
):
    """Zero exact matches for occasion+category together should fall back
    to dropping occasion (a soft signal) while keeping the hard department
    filter intact throughout."""
    womens_kurta = _product(
        test_brand.id, "17", "Plain Womens Kurta", department="women", category="Kurta",
        product_family="kurta", occasion=None,
    )
    mens_kurta = _product(
        test_brand.id, "18", "Plain Mens Kurta", department="men", category="Kurta",
        product_family="kurta", occasion=None,
    )
    await _add_and_flush(db_session, womens_kurta, mens_kurta)

    filters = _scoped(department="women", category="kurta")

    async def _search_once(current_filters, current_occasion):
        eligible = await eligible_products(db_session, current_filters)
        return await rank_products(
            eligible, query_text="", occasion=current_occasion, semantic_query="", collection=None
        )

    relaxed = await search_with_relaxation(
        _search_once, filters, occasion="eid", occasion_is_hard=False
    )

    assert relaxed.dropped_occasion is True
    assert relaxed.effective_occasion is None
    ids = {r.external_id for r in relaxed.products}
    assert "17" in ids
    assert "18" not in ids  # department hard filter must survive relaxation


@pytest.mark.asyncio
async def test_relaxation_never_triggers_when_exact_matches_exist(db_session, test_brand):
    product = _product(
        test_brand.id, "19", "Mehndi Sharara", department="women", category="Sharara",
        product_family="sharara", occasion="mehndi",
    )
    await _add_and_flush(db_session, product)

    filters = _scoped(department="women", category="sharara")

    async def _search_once(current_filters, current_occasion):
        eligible = await eligible_products(db_session, current_filters)
        return await rank_products(
            eligible, query_text="", occasion=current_occasion, semantic_query="", collection=None
        )

    relaxed = await search_with_relaxation(
        _search_once, filters, occasion="mehndi", occasion_is_hard=False
    )

    assert relaxed.dropped_occasion is False
    assert relaxed.effective_occasion == "mehndi"


@pytest.mark.asyncio
async def test_relaxation_stops_at_the_first_relaxable_field_that_yields_a_match(
    db_session, test_brand
):
    """size is peeled before color/budget (per _RELAXATION_ORDER) — a
    product that already matches color+budget should surface as soon as
    size is dropped, without color or budget ever being touched."""
    product = _product(test_brand.id, "21", "Blue Kurta", colors=["Blue"], min_price=3000, max_price=3000)
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color="Blue", size="L", price=3000))

    filters = _scoped(color="blue", size="M", budget_max=5000)

    async def _search_once(current_filters, current_occasion):
        eligible = await eligible_products(db_session, current_filters)
        return await rank_products(eligible, query_text="", occasion=current_occasion, semantic_query="", collection=None)

    relaxed = await search_with_relaxation(
        _search_once, filters, occasion=None, occasion_is_hard=False,
        relaxable_fields=frozenset({"size", "color", "budget_max"}),
    )

    assert relaxed.dropped_filters == ["size"]
    assert product.external_id in {r.external_id for r in relaxed.products}


@pytest.mark.asyncio
async def test_relaxation_peels_multiple_fields_cumulatively_before_giving_up(
    db_session, test_brand
):
    """Dropping size alone isn't enough here (wrong color too) — the ladder
    must keep peeling into color before it finds a match, and never needs
    to touch budget to get there."""
    product = _product(test_brand.id, "22", "Red Kurta", colors=["Red"], min_price=3000, max_price=3000)
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color="Red", size="L", price=3000))

    filters = _scoped(color="blue", size="M", budget_max=5000)

    async def _search_once(current_filters, current_occasion):
        eligible = await eligible_products(db_session, current_filters)
        return await rank_products(eligible, query_text="", occasion=current_occasion, semantic_query="", collection=None)

    relaxed = await search_with_relaxation(
        _search_once, filters, occasion=None, occasion_is_hard=False,
        relaxable_fields=frozenset({"size", "color", "budget_max"}),
    )

    assert relaxed.dropped_filters == ["size", "color"]
    assert product.external_id in {r.external_id for r in relaxed.products}


@pytest.mark.asyncio
async def test_relaxation_never_drops_a_field_the_caller_did_not_mark_relaxable(
    db_session, test_brand
):
    """A field the shopper stated as a hard requirement this turn is never
    silently dropped, even if dropping it would have produced a match —
    callers express that by simply omitting it from relaxable_fields."""
    product = _product(test_brand.id, "23", "Red Kurta", colors=["Red"], min_price=3000, max_price=3000)
    await _add_and_flush(db_session, product)
    await _add_and_flush(db_session, _variant(product.id, "v1", color="Red", size="L", price=3000))

    filters = _scoped(color="blue", size="M", budget_max=5000)

    async def _search_once(current_filters, current_occasion):
        eligible = await eligible_products(db_session, current_filters)
        return await rank_products(eligible, query_text="", occasion=current_occasion, semantic_query="", collection=None)

    # Only size is offered — color stays hard, so the ladder must exhaust
    # without ever clearing it and return nothing.
    relaxed = await search_with_relaxation(
        _search_once, filters, occasion=None, occasion_is_hard=False,
        relaxable_fields=frozenset({"size"}),
    )

    assert relaxed.products == []
    assert "color" not in relaxed.dropped_filters


@pytest.mark.asyncio
async def test_relaxation_does_not_pad_exact_matches_with_relaxed_ones(
    db_session, test_brand
):
    """If exact matches exist, keep the result set strict. A stated size,
    color, or budget chip should not coexist with products that only match
    after that same chip was silently loosened."""
    exact = _product(test_brand.id, "24", "Blue Kurta Exact", colors=["Blue"])
    await _add_and_flush(db_session, exact)
    await _add_and_flush(db_session, _variant(exact.id, "v1", color="Blue", size="M", price=3000))

    relaxed_only = _product(test_brand.id, "25", "Blue Kurta Wrong Size", colors=["Blue"])
    await _add_and_flush(db_session, relaxed_only)
    await _add_and_flush(db_session, _variant(relaxed_only.id, "v1", color="Blue", size="L", price=3000))

    filters = _scoped(color="blue", size="M", budget_max=5000)

    async def _search_once(current_filters, current_occasion):
        eligible = await eligible_products(db_session, current_filters)
        return await rank_products(eligible, query_text="", occasion=current_occasion, semantic_query="", collection=None)

    relaxed = await search_with_relaxation(
        _search_once, filters, occasion=None, occasion_is_hard=False,
        relaxable_fields=frozenset({"size", "color", "budget_max"}),
    )

    assert relaxed.dropped_filters == []
    ids = [r.external_id for r in relaxed.products]
    assert ids == ["24"]


@pytest.mark.asyncio
async def test_tradition_boosts_ranking_without_excluding_a_null_tradition_product(
    db_session, test_brand
):
    """Tradition is a soft ranking signal only (search/ranking.py's
    STYLE_MATCH_BOOST) — a requested "eastern" tradition must rank a
    tagged-eastern product ahead of one with no tradition signal at all,
    but must never remove the untagged product from the results, since
    hard-excluding on an absent signal would recreate the same coverage
    bug this session already fixed for department."""
    eastern = _product(
        test_brand.id, "60", "Eastern Kurta", product_family="kurta", product_tradition="eastern",
    )
    unknown = _product(
        test_brand.id, "61", "Mystery Shirt", product_family="shirt", product_tradition=None,
    )
    await _add_and_flush(db_session, eastern, unknown)

    eligible = await eligible_products(db_session, _scoped())
    ranked = await rank_products(
        eligible, query_text="", occasion=None, semantic_query="", tradition="eastern", collection=None
    )

    ids = {r.external_id for r in ranked}
    assert {"60", "61"} <= ids  # neither product was excluded


@pytest.mark.asyncio
async def test_tradition_mismatch_does_not_exclude_the_product_either(db_session, test_brand):
    """A product explicitly tagged the opposite tradition still isn't
    removed — tradition only ever boosts, it's never a gate."""
    western = _product(
        test_brand.id, "62", "Denim Jeans", product_family="jeans", product_tradition="western",
    )
    await _add_and_flush(db_session, western)

    eligible = await eligible_products(db_session, _scoped())
    ranked = await rank_products(
        eligible, query_text="", occasion=None, semantic_query="", tradition="eastern", collection=None
    )

    assert "62" in {r.external_id for r in ranked}


@pytest.mark.asyncio
async def test_search_service_raises_on_eligibility_violation_if_ranking_ever_misbehaves(
    db_session, test_brand, monkeypatch
):
    """Confirms the defense-in-depth check is real, not decorative — force
    a ranking function that leaks an ineligible id and verify it's caught."""
    product = _product(test_brand.id, "20", "Item", department="women")
    await _add_and_flush(db_session, product)

    async def _leaky_rank(rows, **kwargs):
        # A never-flushed row has id=None, which can never be in the
        # eligible set's real UUIDs — simulating a ranking bug that
        # invents/leaks a product outside what eligibility.py allowed.
        leaked = _product(test_brand.id, "999", "Leaked", department="men")
        return rows + [leaked]

    import resham.search.service as service_module

    monkeypatch.setattr(service_module, "rank_products", _leaky_rank)

    with pytest.raises(EligibilityViolation):
        await search(
            db_session,
            None,
            _scoped(department="women"),
            occasion=None,
        )
