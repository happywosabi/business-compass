"""所有后台接口共用权限边界；解锁与登录共享失败计数。"""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text

from app.auth import passwords
from app.auth.dependencies import CurrentSessionDep
from app.db.base import utcnow
from app.db.models import AdminAudit, User, UserSession
from app.deps import DB


async def management_lock(db):
    await db.execute(text("SELECT pg_advisory_xact_lock(9412272)"))


def audit(db, request, actor_id, action, target, reason, changes=None, result="success"):
    db.add(
        AdminAudit(
            actor_id=actor_id,
            action=action,
            target=str(target),
            reason=reason,
            ip=request.client.host if request.client else None,
            changes=changes or {},
            result=result,
        )
    )


async def admin_identity(db, current, *, lock=False):
    if lock:
        await management_lock(db)
    query = select(User).where(User.id == current.user.id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update(key_share=True)
    user = await db.scalar(query)
    query = (
        select(UserSession)
        .where(UserSession.id == current.session.id)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    session = await db.scalar(query)
    if (
        user is None
        or not user.is_admin
        or user.status != "active"
        or user.deleted_at
        or not user.email_verified_at
    ):
        raise HTTPException(403, "需要管理员权限")
    if (
        session is None
        or session.expires_at <= utcnow()
        or session.password_version != user.password_version
    ):
        raise HTTPException(401, "登录已失效，请重新登录")
    return user, session


async def require_admin(request: Request, db: DB, current: CurrentSessionDep):
    user, session = await admin_identity(db, current, lock=request.method != "GET")
    if session.admin_until is None or session.admin_until <= utcnow():
        raise HTTPException(423, "管理权限已锁定，请重新验证密码")
    return user


Admin = Annotated[User, Depends(require_admin)]


async def unlock(db, current, password, settings, request):
    user, session = await admin_identity(db, current, lock=True)
    if user.locked_until and user.locked_until > utcnow():
        raise HTTPException(429, "登录失败次数过多，请稍后再试")
    valid = await passwords.verify_password(user.password_hash, password)
    if not valid:
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failures:
            user.failed_login_count = 0
            user.locked_until = utcnow() + timedelta(minutes=settings.login_lock_minutes)
            session.admin_until = None
        audit(db, request, user.id, "unlock", user.id, "密码验证", result="failed")
        await db.commit()
        raise HTTPException(401, "密码错误")
    user.failed_login_count, user.locked_until = 0, None
    session.admin_until = utcnow() + timedelta(minutes=15)
    audit(db, request, user.id, "unlock", user.id, "密码验证")
    await db.commit()
    return {"expires_at": session.admin_until}
