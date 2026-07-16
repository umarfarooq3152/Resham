"""Devices API router — anonymous device registration and preferences."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from resham.db.connection import get_session
from resham.repositories.device_repo import DeviceRepository
from resham.schemas.device import DeviceCreateResponse, DeviceResponse, DeviceSizeUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["devices"])


def _mask(device_id: UUID) -> str:
    return f"{str(device_id)[:8]}..."


@router.post("", response_model=DeviceCreateResponse)
async def register_device(
    session: AsyncSession = Depends(get_session),
) -> DeviceCreateResponse:
    try:
        device = await DeviceRepository(session).get_or_create()
        await session.commit()
        logger.info("Registered device %s", _mask(device.device_id))
        return DeviceCreateResponse(device_id=device.device_id, created_at=device.created_at)
    except Exception as error:
        await session.rollback()
        logger.error("Failed to register device: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register device") from error


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> DeviceResponse:
    device = await DeviceRepository(session).get_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceResponse.model_validate(device)


@router.patch("/{device_id}/size", response_model=DeviceResponse)
async def update_device_size(
    device_id: UUID,
    payload: DeviceSizeUpdate,
    session: AsyncSession = Depends(get_session),
) -> DeviceResponse:
    repo = DeviceRepository(session)
    device = await repo.get_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        await repo.update_size(device_id, payload.size)
        await session.commit()
        logger.info("Updated device %s size to %s", _mask(device_id), payload.size)
        return DeviceResponse.model_validate(device)
    except Exception as error:
        await session.rollback()
        logger.error("Failed to update device size: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update device size") from error
