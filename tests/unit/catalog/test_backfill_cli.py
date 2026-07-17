"""_reenrich_row is the core of the backfill: given a ProductRow already in
Postgres (crawled long ago, possibly before a heuristic improved), it must
recompute every derived field from the row's own stored text — no network
call, no dependency on a live crawl succeeding."""

from resham.catalog.backfill_cli import _reenrich_row
from resham.db.models.product import Product as ProductRow


def _row(**overrides) -> ProductRow:
    defaults = dict(
        brand_id=None,
        external_id="1",
        composite_key="brand:1",
        title="Embroidered Kurta",
        description_html="",
        description_text="",
        category="Kurta",
        vendor=None,
        shopify_tags=[],
        tags=[],
        department=None,
        is_kids=False,
        age_ranges_months=[],
        occasion=None,
        colors=[],
        sizes=[],
        color_images={},
        min_price=1000.0,
        max_price=1000.0,
        primary_image_url="https://example.com/a.jpg",
        secondary_image_url=None,
        product_url="https://example.com/products/1",
        product_family=None,
        text_derived_color=None,
        product_tradition=None,
        product_formality=None,
        embedded_at=None,
    )
    defaults.update(overrides)
    return ProductRow(**defaults)


def test_backfill_fills_previously_empty_classification_fields():
    row = _row(title="Embroidered Kurta", category="Kurta")

    changed = _reenrich_row(row, brand_department="unisex")

    assert changed is True
    assert row.product_family == "kurta"
    assert row.product_tradition == "eastern"
    assert row.product_formality is not None
    assert row.embedded_at is None


def test_backfill_never_downgrades_an_existing_department():
    row = _row(title="Item With No Gender Word", category=None, department="women")

    _reenrich_row(row, brand_department="unisex")

    assert row.department == "women"


def test_backfill_applies_brand_fallback_for_a_missing_department():
    row = _row(title="Item With No Gender Word", category=None, department=None)

    _reenrich_row(row, brand_department="men")

    assert row.department == "men"


def test_backfill_is_idempotent_on_a_second_run():
    row = _row(title="Embroidered Kurta", category="Kurta")
    _reenrich_row(row, brand_department="unisex")

    changed_again = _reenrich_row(row, brand_department="unisex")

    assert changed_again is False


def test_backfill_detects_kids_signal_only_present_in_description():
    row = _row(
        title="Crew Neck Graphic Tee",
        category="T-Shirt",
        description_text="Stone-colored blended tee, designed for toddler girls",
    )

    _reenrich_row(row, brand_department="unisex")

    assert row.is_kids is True
