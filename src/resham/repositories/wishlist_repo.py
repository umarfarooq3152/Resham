"""Wishlist repository — data access for wishlist items."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.wishlist import WishlistItem


class WishlistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self, device_id: UUID) -> list[WishlistItem]:
        result = await self.session.execute(
            select(WishlistItem)
            .where(WishlistItem.device_id == device_id)
            .where(WishlistItem.user_id.is_(None))
            .order_by(WishlistItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_product_id(self, device_id: UUID, product_id: UUID) -> WishlistItem | None:
        result = await self.session.execute(
            select(WishlistItem)
            .where(WishlistItem.device_id == device_id)
            .where(WishlistItem.product_id == product_id)
            .where(WishlistItem.user_id.is_(None))
        )
        return result.scalars().first()

    async def add(self, device_id: UUID, product_id: UUID) -> WishlistItem:
        item = WishlistItem(device_id=device_id, product_id=product_id)
        self.session.add(item)
        await self.session.flush()
        return item

    async def remove(self, device_id: UUID, product_id: UUID) -> bool:
        item = await self.get_by_product_id(device_id, product_id)
        if item is None:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True

    async def exists(self, device_id: UUID, product_id: UUID) -> bool:
        return await self.get_by_product_id(device_id, product_id) is not None

    async def get_all_for_user(self, user_id: UUID) -> list[WishlistItem]:
        result = await self.session.execute(
            select(WishlistItem)
            .where(WishlistItem.user_id == user_id)
            .order_by(WishlistItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_product_id_for_user(
        self, user_id: UUID, product_id: UUID
    ) -> WishlistItem | None:
        result = await self.session.execute(
            select(WishlistItem)
            .where(WishlistItem.user_id == user_id)
            .where(WishlistItem.product_id == product_id)
        )
        return result.scalars().first()

    async def add_for_user(self, user_id: UUID, device_id: UUID, product_id: UUID) -> WishlistItem:
        item = WishlistItem(device_id=device_id, product_id=product_id, user_id=user_id)
        self.session.add(item)
        await self.session.flush()
        return item

    async def remove_for_user(self, user_id: UUID, product_id: UUID) -> bool:
        item = await self.get_by_product_id_for_user(user_id, product_id)
        if item is None:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True

    async def exists_for_user(self, user_id: UUID, product_id: UUID) -> bool:
        return await self.get_by_product_id_for_user(user_id, product_id) is not None

    async def claim_device_wishlist(self, device_id: UUID, user_id: UUID) -> None:
        existing = await self.session.execute(
            select(WishlistItem.product_id).where(WishlistItem.user_id == user_id)
        )
        existing_ids = {row[0] for row in existing.all()}

        anon_items = await self.session.execute(
            select(WishlistItem)
            .where(WishlistItem.device_id == device_id)
            .where(WishlistItem.user_id.is_(None))
        )
        for item in anon_items.scalars().all():
            if item.product_id in existing_ids:
                await self.session.delete(item)
            else:
                item.user_id = user_id
                existing_ids.add(item.product_id)
        await self.session.flush()
