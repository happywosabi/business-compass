"""登录注册接口：/api/auth/..."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.config import Settings
from app.deps import DB, AppSettings
from app.mail import MailMessage, send_safely

from . import service
from .dependencies import CurrentSessionDep, CurrentUser
from .schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageOut,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["登录注册"])


def _send_after_response(
    background: BackgroundTasks, request: Request, messages: list[MailMessage]
) -> None:
    sender = request.app.state.mail_sender
    for message in messages:
        background.add_task(send_safely, sender, message)


def _cookie_options(settings: Settings) -> dict:
    return {
        "httponly": True,  # 网页里的 JavaScript 读不到，防止被盗
        "secure": settings.session_cookie_secure,  # 只通过 HTTPS 发送
        "samesite": "lax",  # 其他网站发起的请求不会带上，防止跨站伪造请求
        "path": "/",
    }


@router.post("/register", status_code=201, response_model=MessageOut, summary="注册")
async def register(
    body: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    db: DB,
    settings: AppSettings,
):
    messages = await service.register(db, settings, body.email, body.password)
    _send_after_response(background, request, messages)
    return MessageOut(message="注册成功，验证邮件已发送，请查收")


@router.post("/verify-email", response_model=MessageOut, summary="验证邮箱")
async def verify_email(body: TokenRequest, db: DB):
    await service.verify_email(db, body.token)
    return MessageOut(message="邮箱验证成功")


@router.post("/resend-verification", response_model=MessageOut, summary="重新发送验证邮件")
async def resend_verification(
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    messages = await service.resend_verification(db, settings, user)
    _send_after_response(background, request, messages)
    return MessageOut(message="验证邮件已发送，请查收")


@router.post("/login", response_model=UserOut, summary="登录")
async def login(
    body: LoginRequest, request: Request, response: Response, db: DB, settings: AppSettings
):
    result = await service.login(
        db,
        settings,
        body.email,
        body.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        settings.session_cookie_name,
        result.token,
        max_age=settings.session_days * 24 * 3600,
        **_cookie_options(settings),
    )
    return UserOut.from_user(result.user)


@router.post("/logout", response_model=MessageOut, summary="退出登录")
async def logout(request: Request, response: Response, db: DB, settings: AppSettings):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await service.logout(db, token)
    response.delete_cookie(settings.session_cookie_name, **_cookie_options(settings))
    return MessageOut(message="已退出登录")


@router.get("/me", response_model=UserOut, summary="当前用户")
async def me(user: CurrentUser):
    return UserOut.from_user(user)


@router.post("/forgot-password", response_model=MessageOut, summary="忘记密码")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: DB,
    settings: AppSettings,
):
    messages = await service.forgot_password(db, settings, body.email)
    _send_after_response(background, request, messages)
    return MessageOut(message="如果该邮箱已注册，我们已发送重置密码的邮件，请查收")


@router.post("/reset-password", response_model=MessageOut, summary="重置密码")
async def reset_password(body: ResetPasswordRequest, db: DB):
    await service.reset_password(db, body.token, body.new_password)
    return MessageOut(message="密码已重置，请用新密码登录")


@router.post("/change-password", response_model=MessageOut, summary="修改密码")
async def change_password(body: ChangePasswordRequest, current: CurrentSessionDep, db: DB):
    await service.change_password(db, current, body.old_password, body.new_password)
    return MessageOut(message="密码已修改，其他设备已退出登录")
