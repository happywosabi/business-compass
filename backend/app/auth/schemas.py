"""接口的请求和响应格式。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models import User

from .passwords import MAX_LENGTH

Password = Field(min_length=1, max_length=MAX_LENGTH)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Password


class TokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Password


class ChangePasswordRequest(BaseModel):
    old_password: str = Password
    new_password: str = Password


class MessageOut(BaseModel):
    message: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    nickname: str | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserOut:
        return cls(
            id=user.id,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            nickname=user.nickname,
            created_at=user.created_at,
        )
