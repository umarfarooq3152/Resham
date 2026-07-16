"""User repository — data access for registered accounts."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalars().first()

    async def create(self, email: str, password_hash: str, name: str) -> User:
        user = User(email=email.lower(), password_hash=password_hash, name=name)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_profile(
        self,
        user_id: UUID,
        *,
        name: str | None = None,
        preferred_size: str | None = None,
        department: str | None = None,
    ) -> Optional[User]:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        if name is not None:
            user.name = name
        if preferred_size is not None:
            user.preferred_size = preferred_size
        if department is not None:
            user.department = department
        await self.session.flush()
        return user
