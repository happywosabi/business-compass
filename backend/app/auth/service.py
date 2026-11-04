"""登录注册的业务逻辑。

对应文档：商业档案数据结构 第四节（登录流程、安全与防刷）。
需要发送的邮件由函数返回，交给接口层在响应之后再发送，这样发信慢或失败都不会拖慢接口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.base import utcnow
from app.db.models import EmailToken, User, UserSession
from app.logs import mask_email
from app.mail import MailMessage
from app.mail.templates import password_reset_email, verification_email

from . import passwords
from .email_rules import is_disposable, normalize_email
from .tokens import hash_token, new_token

logger = logging.getLogger(__name__)

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"

# 每次请求都更新"最近活跃时间"会产生大量写入，所以最多 10 分钟更新一次
LAST_SEEN_UPDATE_INTERVAL = timedelta(minutes=10)


class AuthError(Exception):
    """可以直接展示给用户的错误。"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class LoginResult:
    user: User
    token: str  # 放进 Cookie 的会话令牌原文


@dataclass
class CurrentSession:
    user: User
    session: UserSession


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _check_new_password(password: str, email: str) -> None:
    try:
        passwords.check_password_strength(password, email)
    except passwords.WeakPasswordError as error:
        raise AuthError(400, str(error)) from error


def _link(settings: Settings, path: str, token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}?token={token}"


async def _find_user(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))


async def _issue_email_token(
    db: AsyncSession, settings: Settings, user: User, purpose: str
) -> str | None:
    """生成一个邮件令牌；发送太频繁时返回 None。调用方负责提交事务。"""
    now = utcnow()
    same_purpose = (EmailToken.user_id == user.id, EmailToken.purpose == purpose)

    last_sent = await db.scalar(select(func.max(EmailToken.created_at)).where(*same_purpose))
    if last_sent and now - last_sent < timedelta(seconds=settings.email_resend_seconds):
        return None
    sent_today = await db.scalar(
        select(func.count())
        .select_from(EmailToken)
        .where(*same_purpose, EmailToken.created_at > now - timedelta(days=1))
    )
    if sent_today >= settings.email_daily_limit:
        logger.warning("邮件发送达到每日上限：%s（%s）", mask_email(user.email), purpose)
        return None

    # 同一用途只保留最新的一个令牌有效
    await db.execute(
        update(EmailToken).where(*same_purpose, EmailToken.used_at.is_(None)).values(used_at=now)
    )
    if purpose == VERIFY_EMAIL:
        ttl = timedelta(hours=settings.verify_token_hours)
    else:
        ttl = timedelta(minutes=settings.reset_token_minutes)
    token = new_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=now + ttl,
            created_at=now,
        )
    )
    return token


async def _take_email_token(
    db: AsyncSession, token: str, purpose: str
) -> tuple[EmailToken, User] | None:
    """找到一个有效（未使用、未过期）的邮件令牌，并锁住这一行，防止同时被使用两次。"""
    row = (
        await db.execute(
            select(EmailToken, User)
            .join(User, User.id == EmailToken.user_id)
            .where(
                EmailToken.token_hash == hash_token(token),
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > utcnow(),
                User.deleted_at.is_(None),
            )
            .with_for_update(of=EmailToken)
        )
    ).first()
    return (row[0], row[1]) if row else None


def _verification_mail(settings: Settings, user: User, token: str) -> MailMessage:
    link = _link(settings, "/verify-email", token)
    return verification_email(user.email, link, settings.verify_token_hours)


# ---------------------------------------------------------------------------
# 注册和验证邮箱
# ---------------------------------------------------------------------------


async def register(
    db: AsyncSession, settings: Settings, email: str, password: str
) -> list[MailMessage]:
    email = normalize_email(email)
    if is_disposable(email):
        raise AuthError(400, "暂不支持临时邮箱注册，请使用常用邮箱")
    _check_new_password(password, email)

    already = AuthError(409, "该邮箱已注册，请直接登录；忘记密码可以重置")
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise already

    user = User(email=email, password_hash=await passwords.hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as error:  # 两个请求同时用同一个邮箱注册
        await db.rollback()
        raise already from error

    token = await _issue_email_token(db, settings, user, VERIFY_EMAIL)
    await db.commit()
    logger.info("新用户注册：%s", mask_email(email))
    return [_verification_mail(settings, user, token)] if token else []


async def verify_email(db: AsyncSession, token: str) -> None:
    found = await _take_email_token(db, token, VERIFY_EMAIL)
    if found is None:
        raise AuthError(400, "链接无效或已过期，请登录后重新发送验证邮件")
    email_token, user = found
    now = utcnow()
    email_token.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    await db.commit()


async def resend_verification(
    db: AsyncSession, settings: Settings, user: User
) -> list[MailMessage]:
    if user.email_verified_at is not None:
        raise AuthError(400, "邮箱已经验证过了")
    token = await _issue_email_token(db, settings, user, VERIFY_EMAIL)
    if token is None:
        raise AuthError(429, "邮件发送太频繁，请稍后再试")
    await db.commit()
    return [_verification_mail(settings, user, token)]


# ---------------------------------------------------------------------------
# 登录、会话、退出
# ---------------------------------------------------------------------------


async def login(
    db: AsyncSession,
    settings: Settings,
    email: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> LoginResult:
    email = normalize_email(email)
    wrong = AuthError(401, "邮箱或密码错误")
    locked = AuthError(429, f"登录失败次数过多，请 {settings.login_lock_minutes} 分钟后再试")
    now = utcnow()

    user = await _find_user(db, email)
    if user is None:
        await passwords.burn_verify_time(password)
        raise wrong
    if user.locked_until and user.locked_until > now:
        raise locked

    if not await passwords.verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failures:
            user.failed_login_count = 0
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            await db.commit()
            logger.warning("账号因多次登录失败被锁定：%s", mask_email(email))
            raise locked
        await db.commit()
        raise wrong

    if user.status != "active":
        raise AuthError(403, "账号已停用，请联系客服")

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = await passwords.hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(days=settings.session_days),
            created_at=now,
            last_seen_at=now,
            ip=ip,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    await db.commit()
    return LoginResult(user=user, token=token)


async def authenticate(db: AsyncSession, token: str | None) -> CurrentSession | None:
    """根据 Cookie 里的令牌找到当前用户；令牌无效、过期或账号不可用时返回 None。"""
    if not token:
        return None
    now = utcnow()
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.expires_at > now,
                User.deleted_at.is_(None),
                User.status == "active",
            )
        )
    ).first()
    if row is None:
        return None
    session, user = row
    if now - session.last_seen_at > LAST_SEEN_UPDATE_INTERVAL:
        session.last_seen_at = now
        await db.commit()
    return CurrentSession(user=user, session=session)


async def logout(db: AsyncSession, token: str) -> None:
    await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    await db.commit()


# ---------------------------------------------------------------------------
# 忘记密码、重置密码、修改密码
# ---------------------------------------------------------------------------


async def forgot_password(db: AsyncSession, settings: Settings, email: str) -> list[MailMessage]:
    """无论邮箱是否注册，接口都返回同样的提示，避免被用来探测谁注册过。"""
    user = await _find_user(db, normalize_email(email))
    if user is None or user.status != "active":
        return []
    token = await _issue_email_token(db, settings, user, RESET_PASSWORD)
    await db.commit()
    if token is None:
        return []
    link = _link(settings, "/reset-password", token)
    return [password_reset_email(user.email, link, settings.reset_token_minutes)]


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    found = await _take_email_token(db, token, RESET_PASSWORD)
    if found is None:
        raise AuthError(400, "链接无效或已过期，请重新申请重置密码")
    email_token, user = found
    # 新密码不合格时直接报错，令牌不会被用掉，用户改个密码再提交即可
    _check_new_password(new_password, user.email)

    now = utcnow()
    user.password_hash = await passwords.hash_password(new_password)
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    if user.email_verified_at is None:
        user.email_verified_at = now  # 能收到重置邮件，说明邮箱确实属于本人
    email_token.used_at = now
    # 所有设备退出登录
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.commit()


async def change_password(
    db: AsyncSession, current: CurrentSession, old_password: str, new_password: str
) -> None:
    user = current.user
    if not await passwords.verify_password(user.password_hash, old_password):
        raise AuthError(400, "原密码错误")
    if new_password == old_password:
        raise AuthError(400, "新密码不能和原密码相同")
    _check_new_password(new_password, user.email)

    user.password_hash = await passwords.hash_password(new_password)
    user.password_changed_at = utcnow()
    # 其他设备退出登录，当前设备保持登录
    await db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.id != current.session.id
        )
    )
    await db.commit()
