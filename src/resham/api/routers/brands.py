"""Brand listing API for the web frontend."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.connection import get_session
from resham.repositories.brand_repo import BrandRepository
from resham.schemas.brand import BrandResponse

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("", response_model=list[BrandResponse])
async def list_brands(
    department: Optional[str] = Query(None, pattern="^(men|women|unisex)$"),
    session: AsyncSession = Depends(get_session),
) -> list[BrandResponse]:
    brands = await BrandRepository(session).get_all_active(department=department)
    return [BrandResponse.model_validate(brand) for brand in brands]
