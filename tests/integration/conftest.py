"""Shared fixtures for integration tests — these run against the real dev
Postgres (docker-compose `postgres` service), not an in-memory substitute,
since the eligibility gate's correctness depends on real SQL semantics and
the `product_variants` join."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from resham.config import get_settings
from resham.db.models.brand import Brand


@pytest_asyncio.fixture
async def db_session():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_brand(db_session):
    """An isolated brand for this test only — cascades delete its
    products/variants on teardown so tests never depend on or pollute the
    real crawled catalog."""
    brand = Brand(name="Test Brand", slug="test-brand-fixture", domain="test-brand.example", department="unisex")
    db_session.add(brand)
    await db_session.commit()
    yield brand
    await db_session.delete(brand)
    await db_session.commit()
