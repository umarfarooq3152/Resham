"""Tests for row_to_pydantic_product's opt-in variants/brand_domain —
added for the cart hand-off feature. variants/brand_domain must be passed
in explicitly (never read off row.variants, the lazy relationship that's
unsafe to touch under async SQLAlchemy without eager loading — see
catalog/repository.py's _upsert_variants docstring for the same hazard)."""

from decimal import Decimal
from uuid import uuid4

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.models.product import Product as ProductRow
from resham.db.models.product_variant import ProductVariant as VariantRow


def _product_row(**overrides) -> ProductRow:
    defaults = dict(
        id=uuid4(),
        brand_id=uuid4(),
        external_id="1",
        composite_key="brand:1",
        title="Embroidered Kurta",
        min_price=Decimal("4500"),
        colors=["Blue"],
        sizes=["M"],
        color_images={},
        is_kids=False,
        tags=[],
        shopify_tags=[],
        age_ranges_months=[],
        primary_image_url="https://cdn.example/a.jpg",
        product_url="https://example.com/products/1",
    )
    defaults.update(overrides)
    return ProductRow(**defaults)


def test_variants_and_brand_domain_are_empty_by_default():
    product = row_to_pydantic_product(_product_row())

    assert product.variants == []
    assert product.brand_domain is None


def test_passed_in_variants_are_mapped_with_real_shopify_ids():
    row = _product_row()
    variants = [
        VariantRow(
            product_id=row.id,
            external_variant_id="44112233",
            color="Blue",
            size="M",
            price=Decimal("4500"),
            available=True,
        ),
        VariantRow(
            product_id=row.id,
            external_variant_id="44112234",
            color="Blue",
            size="L",
            price=Decimal("4500"),
            available=False,
        ),
    ]

    product = row_to_pydantic_product(row, variants=variants, brand_domain="www.example.pk")

    assert product.brand_domain == "www.example.pk"
    assert [v.model_dump() for v in product.variants] == [
        {"variant_id": "44112233", "color": "Blue", "size": "M", "price": 4500.0, "available": True},
        {"variant_id": "44112234", "color": "Blue", "size": "L", "price": 4500.0, "available": False},
    ]
