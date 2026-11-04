"""登录相关的 FastAPI 依赖：在接口里获取当前用户。

用法：
    @router.get("/xxx")
    async def xxx(user: CurrentUser): ...           # 需要登录
    async def yyy(user: VerifiedUser): ...          # 需要登录且已验证邮箱（AI 功能用这个）
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.db.models import User
from app.deps import DB, AppSettings

from . import service
from .service import CurrentSession


async def get_current_session(request: Request, db: DB, settings: AppSettings) -> CurrentSession:
    current = await service.authenticate(db, request.cookies.get(settings.session_cookie_name))
    if current is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return current


async def get_current_user(
    current: Annotated[CurrentSession, Depends(get_current_session)],
) -> User:
    return current.user


async def require_verified_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="请先验证邮箱")
    return user


CurrentSessionDep = Annotated[CurrentSession, Depends(get_current_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(require_verified_user)]
