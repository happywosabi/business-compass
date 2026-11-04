"""接口测试的辅助函数。"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import EmailToken, User
from app.mail import MailMessage

EMAIL = "user@example.com"
PASSWORD = "correct-horse-42"
NEW_PASSWORD = "battery-staple-77"


def token_from(message: MailMessage) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", message.text)
    assert match, "邮件里没有找到链接令牌"
    return match.group(1)


async def register(client, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/api/auth/register", json={"email": email, "password": password})


async def login(client, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def verify(client, outbox: list[MailMessage]):
    return await client.post("/api/auth/verify-email", json={"token": token_from(outbox[-1])})


async def get_user(db: AsyncSession, email: str = EMAIL) -> User:
    db.expire_all()
    return await db.scalar(select(User).where(User.email == email))


async def backdate_email_tokens(db: AsyncSession, minutes: int = 2) -> None:
    """把已发的邮件令牌都往前挪几分钟，用来绕过"60 秒内只能发一次"的限制。"""
    await db.execute(
        update(EmailToken).values(created_at=EmailToken.created_at - timedelta(minutes=minutes))
    )
    await db.commit()


async def expire_email_tokens(db: AsyncSession) -> None:
    await db.execute(update(EmailToken).values(expires_at=utcnow() - timedelta(minutes=1)))
    await db.commit()
