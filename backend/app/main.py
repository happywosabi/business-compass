"""FastAPI 应用入口。

启动方式（Dockerfile 中）：uvicorn --factory app.main:create_app
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.auth.service import AuthError
from app.config import Settings, get_settings
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

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(profiles_router)
    app.include_router(evaluations_router)
    app.include_router(interview_router)
    app.include_router(reports_router)
    app.include_router(content_router)

    _warn_about_settings(settings)
    return app
