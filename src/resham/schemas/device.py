"""Schemas for anonymous device registration and preferences."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DeviceCreateResponse(BaseModel):
    device_id: UUID
    created_at: datetime


class DeviceSizeUpdate(BaseModel):
    size: str = Field(..., min_length=1, max_length=10)


class DeviceResponse(BaseModel):
    device_id: UUID
    size: str | None = None
    created_at: datetime
    last_seen_at: datetime

    class Config:
        from_attributes = True
