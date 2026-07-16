"""Request/response schemas for auth endpoints."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    name: str = Field(..., min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    preferred_size: str | None = None
    department: str | None = None

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    preferred_size: str | None = Field(None, max_length=10)
    department: str | None = Field(None, max_length=20)
