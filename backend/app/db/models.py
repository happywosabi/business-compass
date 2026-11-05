"""数据库表定义。

对应文档：商业档案数据结构 第四节（用户与登录）。
商业档案的工作稿与参数修改记录也在这里定义。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class Profile(Base):
    """当前可编辑的商业档案；修改时必须校验 revision。"""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    template_key: Mapped[str] = mapped_column(Text, default="physical_store")
    template_version: Mapped[int] = mapped_column(Integer, default=1)
    industry: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text, default="idea")
    status: Mapped[str] = mapped_column(Text, default="draft")
    opened_on: Mapped[date | None] = mapped_column(Date)
    value_proposition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    brand_voice: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = _timestamp()

    __table_args__ = (
        CheckConstraint("stage IN ('idea', 'preparing', 'operating')", name="stage"),
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="status"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index(None, "user_id", "deleted_at", "updated_at"),
    )


class ParameterChange(Base):
    """与参数写入同一事务提交的历史记录。"""

    __tablename__ = "parameter_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    profile_revision: Mapped[int] = mapped_column(Integer)
    parameter_key: Mapped[str] = mapped_column(Text)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)

    __table_args__ = (Index(None, "profile_id", "created_at"),)


class Evaluation(Base):
    """不可变的测算结果与参数副本；仅标签可修改。"""

    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    profile_revision: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(Text, default="user_request")
    label: Mapped[str | None] = mapped_column(Text)
    template_key: Mapped[str] = mapped_column(Text)
    template_version: Mapped[int] = mapped_column(Integer)
    engine_version: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)

    __table_args__ = (Index(None, "profile_id", "created_at"),)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)


class AIRun(Base):
    """一次幂等 AI 请求；先预占日配额，成功或失败均保留用量记录。"""

    __tablename__ = "ai_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="running")
    model: Mapped[str] = mapped_column(Text)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = _timestamp()
    lease_until: Mapped[datetime] = _timestamp(nullable=False)

    __table_args__ = (
        Index(None, "user_id", "created_at"),
        Index("uq_ai_runs_user_request", "user_id", "request_id", unique=True),
    )


class Message(Base):
    """模型协议消息；工具调用与回复成对持久化，完整保存 reasoning_content。"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_runs.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prompt_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)
    __table_args__ = (Index(None, "conversation_id", "created_at", "ordinal"),)


class EvaluationReport(Base):
    """AI 解读独立存储，不修改财务快照。"""

    __tablename__ = "evaluation_reports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), unique=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_runs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)


class ContentDraft(Base):
    """来源与生成结果一起保存，仅由用户复制发布。"""

    __tablename__ = "content_drafts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="CASCADE"), unique=True
    )
    platform: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="running")
    created_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)
    __table_args__ = (Index(None, "profile_id", "created_at"),)


class HotTopic(Base):
    """受限热点来源；保存实际取得的摘要、发布时间及来源。"""

    __tablename__ = "hot_topics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    previous_rank: Mapped[int | None] = mapped_column(Integer)
    safe: Mapped[bool] = mapped_column(default=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    fetched_at: Mapped[datetime] = _timestamp(nullable=False, default=utcnow)
    __table_args__ = (Index(None, "safe", "fetched_at"),)
