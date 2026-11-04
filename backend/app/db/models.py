"""数据库表定义。

对应文档：商业档案数据结构 第四节（用户与登录）。
本阶段只有登录相关的三张表；商业档案等表在后续阶段添加。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


def _timestamp(nullable: bool = True, **kwargs) -> Mapped:
    return mapped_column(DateTime(timezone=True), nullable=nullable, **kwargs)


class User(Base):
    """用户。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)  # 统一转成小写后存储
    email_verified_at: Mapped[datetime | None] = _timestamp()
    password_hash: Mapped[str] = mapped_column(Text)  # Argon2id，不存密码原文
    password_changed_at: Mapped[datetime] = _timestamp(
        nullable=False, default=utcnow, server_default=func.now()
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = _timestamp()
    phone: Mapped[str | None] = mapped_column(Text)  # 预留，暂不使用
    nickname: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    daily_ai_quota: Mapped[int | None] = mapped_column(Integer)  # 为空时使用系统默认值
    last_login_at: Mapped[datetime | None] = _timestamp()
    created_at: Mapped[datetime] = _timestamp(
        nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = _timestamp(
        nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = _timestamp()

    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )


class UserSession(Base):
    """登录会话。浏览器 Cookie 里是令牌原文，数据库只存它的哈希值。"""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = _timestamp(nullable=False)
    created_at: Mapped[datetime] = _timestamp(
        nullable=False, default=utcnow, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = _timestamp(
        nullable=False, default=utcnow, server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)


class EmailToken(Base):
    """验证邮箱、重置密码用的一次性令牌。邮件链接里是原文，数据库只存哈希值。"""

    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = _timestamp(nullable=False)
    used_at: Mapped[datetime | None] = _timestamp()
    created_at: Mapped[datetime] = _timestamp(
        nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="purpose"),
        Index(None, "user_id", "purpose", "created_at"),
    )
