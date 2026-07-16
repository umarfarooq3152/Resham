"""Product repository helpers for API surfaces outside search/chat."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.product import Product as ProductRow


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, product_id: UUID) -> ProductRow | None:
        return await self.session.get(ProductRow, product_id)

    async def get_by_composite_key(self, composite_key: str) -> ProductRow | None:
        result = await self.session.execute(
            select(ProductRow).where(ProductRow.composite_key == composite_key)
        )
        return result.scalars().first()

    async def get_by_ids(self, product_ids: list[UUID]) -> list[ProductRow]:
        if not product_ids:
            return []
        result = await self.session.execute(
            select(ProductRow).where(ProductRow.id.in_(product_ids))
        )
        return list(result.scalars().all())
