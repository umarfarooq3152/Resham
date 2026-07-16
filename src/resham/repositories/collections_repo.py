"""Collections repository — data access for curated collections."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.collections import Collection


class CollectionsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_active(self) -> list[Collection]:
        result = await self.session.execute(
            select(Collection).where(Collection.is_active.is_(True)).order_by(Collection.sort_order)
        )
        return list(result.scalars().all())

    async def get_by_id(self, collection_id: UUID) -> Collection | None:
        return await self.session.get(Collection, collection_id)
