"""Coverage for catalog/repository.py's department fallback: ~38% of live
products name no gender word anywhere in title/category/tags, and used to
be hard-excluded from every department-filtered search as a result — a
single-gender brand's product IS that brand's department, not a guess."""

import pytest
from sqlalchemy import select

from resham.catalog.mapper import MappedProduct
from resham.catalog.repository import upsert_brand_products
from resham.db.models.product import Product as ProductRow


def _mapped(external_id: str, title: str, *, department: str | None) -> MappedProduct:
    return MappedProduct(
        external_id=external_id,
        handle=f"item-{external_id}",
        title=title,
        description_html="",
        description_text="",
        category=None,
        vendor=None,
        shopify_tags=[],
        is_kids=False,
        department=department,
        age_ranges_months=[],
        primary_image_url="https://example.com/a.jpg",
        secondary_image_url=None,
        product_url=f"https://example.com/products/{external_id}",
        variants=[],
        raw_shopify_json={},
    )


@pytest.mark.asyncio
async def test_unnamed_department_falls_back_to_the_brands_curated_department(
    db_session, test_brand
):
    test_brand.department = "women"
    await db_session.flush()

    mapped = _mapped("100", "Signature Piece 5001", department=None)
    await upsert_brand_products(db_session, test_brand.id, test_brand.slug, [mapped])
    await db_session.commit()

    row = (
        await db_session.execute(
            select(ProductRow).where(
                ProductRow.brand_id == test_brand.id, ProductRow.external_id == "100"
            )
        )
    ).scalar_one()
    assert row.department == "women"


@pytest.mark.asyncio
async def test_an_explicit_text_signal_still_wins_over_the_brand_fallback(
    db_session, test_brand
):
    test_brand.department = "women"
    await db_session.flush()

    mapped = _mapped("101", "Men's Kurta", department="men")
    await upsert_brand_products(db_session, test_brand.id, test_brand.slug, [mapped])
    await db_session.commit()

    row = (
        await db_session.execute(
            select(ProductRow).where(
                ProductRow.brand_id == test_brand.id, ProductRow.external_id == "101"
            )
        )
    ).scalar_one()
    assert row.department == "men"
