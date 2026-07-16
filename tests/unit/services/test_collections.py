from types import SimpleNamespace
from uuid import uuid4

import pytest
from resham.services import collections


def test_build_collection_filters_maps_definition():
    filters, meta = collections.build_collection_filters(
        {
            "query": "blue kurta",
            "occasion": "eid",
            "colors": ["blue"],
            "brands": ["zellbury"],
            "excluded_brands": ["limelight"],
            "wants_kids": True,
            "child_age_months": 24,
            "min_price": 1000,
            "max_price": 5000,
        }
    )

    assert filters.color == "blue"
    assert filters.brands == ["zellbury"]
    assert filters.excluded_brands == ["limelight"]
    assert filters.wants_kids is True
    assert filters.child_age_months == 24
    assert filters.budget_min == 1000
    assert filters.budget_max == 5000
    assert meta["occasion"] == "eid"
    assert meta["query_text"] == "blue kurta"


@pytest.mark.asyncio
async def test_resolve_collection_products_applies_tag_filter(monkeypatch):
    first = SimpleNamespace(
        id=uuid4(),
        composite_key="zellbury:1",
        title="Blue Kurta",
        description_text="",
        min_price=2500,
        colors=["Blue"],
        color_images={},
        sizes=["M"],
        occasion="eid",
        category="kurta",
        tags=["festive"],
        shopify_tags=["eid"],
        is_kids=False,
        department="women",
        age_ranges_months=[],
        primary_image_url="https://example.com/1.jpg",
        secondary_image_url=None,
        product_url="https://example.com/1",
    )
    second = SimpleNamespace(
        id=uuid4(),
        composite_key="zellbury:2",
        title="Plain Kurta",
        description_text="",
        min_price=2000,
        colors=["Blue"],
        color_images={},
        sizes=["M"],
        occasion="eid",
        category="kurta",
        tags=["casual"],
        shopify_tags=[],
        is_kids=False,
        department="women",
        age_ranges_months=[],
        primary_image_url="https://example.com/2.jpg",
        secondary_image_url=None,
        product_url="https://example.com/2",
    )

    async def fake_search(session, vector_collection, filters, **kwargs):
        return SimpleNamespace(
            products=[first, second],
            total=2,
            effective_occasion="eid",
            effective_category="kurta",
            dropped_occasion=False,
            dropped_category=False,
        )

    monkeypatch.setattr(collections, "run_search", fake_search)
    collection_row = SimpleNamespace(
        id=uuid4(),
        title="Eid Picks",
        subtitle=None,
        description=None,
        image_url=None,
        filter_definition={"query": "blue kurta", "tags": ["festive"]},
    )

    result = await collections.resolve_collection_products(
        object(),
        None,
        collection_row,
        page=1,
        page_size=20,
    )

    assert result.total == 1
    assert result.items[0].id == "zellbury:1"
