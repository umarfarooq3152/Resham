"""Shared FastAPI dependencies for auth-aware endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.connection import get_session
from resham.repositories.user_repo import UserRepository
from resham.security import decode_access_token


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None


async def get_current_user_id_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[UUID]:
    token = _extract_token(authorization)
    if not token:
        return None
    return decode_access_token(token)


async def get_current_user(
    user_id: Optional[UUID] = Depends(get_current_user_id_optional),
    session: AsyncSession = Depends(get_session),
):
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
