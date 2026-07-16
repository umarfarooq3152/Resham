"""Auth API router — signup, login, and profile management."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from resham.api.rate_limit import limiter
from resham.config import get_settings
from resham.db.connection import get_session
from resham.db.models.user import User
from resham.dependencies import get_current_user
from resham.repositories.user_repo import UserRepository
from resham.repositories.wishlist_repo import WishlistRepository
from resham.schemas.auth import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UpdateProfileRequest,
    UserResponse,
)
from resham.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-used-only-for-timing-safety")


async def _claim_device_wishlist_if_present(
    session: AsyncSession, user_id: UUID, device_id: Optional[UUID]
) -> None:
    if device_id is None:
        return
    try:
        async with session.begin_nested():
            await WishlistRepository(session).claim_device_wishlist(device_id, user_id)
    except Exception as error:
        logger.error(
            "Failed to claim device wishlist for user %s: %s",
            user_id,
            error,
            exc_info=True,
        )


@router.post("/signup", response_model=AuthResponse)
@limiter.limit(f"{get_settings().rate_limit_auth_per_min}/minute")
async def signup(
    request: Request,
    payload: SignupRequest,
    x_device_id: Optional[UUID] = Header(None, alias="X-Device-Id"),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    try:
        user_repo = UserRepository(session)
        if await user_repo.get_by_email(payload.email):
            raise HTTPException(status_code=409, detail="An account with this email already exists")

        user = await user_repo.create(
            email=payload.email,
            password_hash=hash_password(payload.password),
            name=payload.name,
        )
        await _claim_device_wishlist_if_present(session, user.id, x_device_id)
        await session.commit()
        return AuthResponse(
            user=UserResponse.model_validate(user),
            token=create_access_token(user.id),
        )
    except HTTPException:
        raise
    except Exception as error:
        await session.rollback()
        logger.error("Signup failed: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Signup failed") from error


@router.post("/login", response_model=AuthResponse)
@limiter.limit(f"{get_settings().rate_limit_auth_per_min}/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    x_device_id: Optional[UUID] = Header(None, alias="X-Device-Id"),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    try:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_email(payload.email)
        password_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(payload.password, password_hash)
        if not user or not password_ok:
            raise HTTPException(status_code=401, detail="Incorrect email or password")

        await _claim_device_wishlist_if_present(session, user.id, x_device_id)
        await session.commit()
        return AuthResponse(
            user=UserResponse.model_validate(user),
            token=create_access_token(user.id),
        )
    except HTTPException:
        raise
    except Exception as error:
        await session.rollback()
        logger.error("Login failed: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed") from error


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    try:
        updated = await UserRepository(session).update_profile(
            user.id,
            name=payload.name,
            preferred_size=payload.preferred_size,
            department=payload.department,
        )
        await session.commit()
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse.model_validate(updated)
    except HTTPException:
        raise
    except Exception as error:
        await session.rollback()
        logger.error("Failed to update profile for %s: %s", user.id, error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update profile") from error
