"""FastAPI 应用入口。

启动方式（Dockerfile 中）：uvicorn --factory app.main:create_app
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.admin.router import router as admin_router
from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.auth.service import AuthError
from app.config import Settings, get_settings
from app.confirmations import router as confirmations_router
from app.content.router import router as content_router
from app.db.session import create_engine, create_session_factory
from app.evaluations.router import router as evaluations_router
from app.interview.router import router as interview_router
from app.interview.service import Coordinator
from app.llm.provider import DeepSeekProvider
from app.llm.reports import router as reports_router
from app.logs import setup_logging
from app.mail import MailSender, create_mail_sender
from app.profiles.router import router as profiles_router

logger = logging.getLogger(__name__)


def _warn_about_settings(settings: Settings) -> None:
    password = settings.postgres_password.get_secret_value()
    if password in {"", "change-me"} and not settings.database_url:
        logger.warning("数据库密码为空或仍是模板里的 change-me，请在 .env 中修改")
    if settings.is_production:
        if settings.mail_backend != "smtp":
            logger.warning("生产环境的 MAIL_BACKEND 不是 smtp，用户将收不到邮件")


def create_app(settings: Settings | None = None, mail_sender: MailSender | None = None) -> FastAPI:
    """创建应用。测试时可以传入自己的配置和邮件发送器。"""
    settings = settings or get_settings()
    settings.production_security()
    setup_logging()
    engine = create_engine(settings.sqlalchemy_url())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.ai_hub.close()
        await engine.dispose()

    # 接口文档只在非生产环境开放
    show_docs = not settings.is_production
    app = FastAPI(
        title="商业罗盘 API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if show_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if show_docs else None,
    )
    app.state.ai_hub = Coordinator()
    app.state.llm = DeepSeekProvider(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine, settings)
    app.state.mail_sender = mail_sender or create_mail_sender(settings)

    @app.exception_handler(AuthError)
    async def handle_auth_error(request: Request, error: AuthError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, error: DBAPIError):
        if "compass_document_limit" in str(error.orig):
            return JSONResponse(
                status_code=422, content={"detail": "单份档案最多256KiB，请缩短资料"}
            )
        if "compass_profile_limit" in str(error.orig):
            return JSONResponse(
                status_code=429, content={"detail": "档案数量已达上限，请清理旧档案"}
            )
        if "compass_storage_limit" in str(error.orig):
            return JSONResponse(
                status_code=429, content={"detail": "账号存储额度已用完，请删除或缩减旧资料"}
            )
        logger.error("Database request failed: %s", type(error).__name__)
        return JSONResponse(status_code=500, content={"detail": "服务暂时不可用，请稍后重试"})

    @app.middleware("http")
    async def admin_boundary(request: Request, call_next):
        if request.url.path.startswith("/api/admin"):
            if request.method not in {"GET", "HEAD", "OPTIONS"} and (
                request.headers.get("origin") != settings.app_base_url.rstrip("/")
                or request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "请从本站后台提交操作"},
                    headers={"Cache-Control": "no-store"},
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            if (
                request.method == "POST"
                and response.status_code >= 400
                and request.url.path != "/api/admin/unlock"
            ):
                # 失败记录独立提交，不保存请求正文或用户提供的敏感文本。
                from app.auth.service import authenticate
                from app.db.models import AdminAudit

                async with app.state.session_factory() as audit_db:
                    current = await authenticate(
                        audit_db, request.cookies.get(settings.session_cookie_name)
                    )
                    if current and current.user.is_admin:
                        audit_db.add(
                            AdminAudit(
                                actor_id=current.user.id,
                                action="request.rejected",
                                target=request.url.path.removeprefix("/api/admin/"),
                                reason=f"操作未完成（HTTP {response.status_code}）",
                                ip=request.client.host if request.client else None,
                                result="failed",
                                changes={},
                            )
                        )
                        await audit_db.commit()
            return response
        return await call_next(request)

    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(profiles_router)
    app.include_router(evaluations_router)
    app.include_router(interview_router)
    app.include_router(reports_router)
    app.include_router(content_router)
    app.include_router(confirmations_router)

    _warn_about_settings(settings)
    return app
