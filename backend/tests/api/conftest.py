"""接口测试的准备工作。

接口测试需要一个 PostgreSQL：
- 默认连接 .env 里配置的数据库服务器，使用库名加 _test 后缀的测试库（不存在会自动创建）
- 也可以用环境变量 TEST_DATABASE_URL 指定
- 连接不上时，这些测试会被跳过（计算引擎等其他测试照常运行）

邮件不会真正发送，而是存进内存里的 outbox，测试可以从中读取邮件内容。
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db import models  # noqa: F401  导入表定义
from app.db.base import Base
from app.mail import MemoryMailSender
from app.main import create_app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


def _test_settings() -> Settings:
    base = Settings()
    url = os.environ.get("TEST_DATABASE_URL") or base.sqlalchemy_url(
        database=f"{base.postgres_db}_test"
    )
    return base.model_copy(
        update={
            "app_env": "test",
            "database_url": url,
            "app_base_url": "http://testserver",
            "session_cookie_secure": False,
            "mail_backend": "console",
        }
    )


@pytest.fixture(scope="session")
async def test_settings(anyio_backend) -> Settings:
    """准备测试库：不存在则创建，然后按当前表定义重建所有表。"""
    settings = _test_settings()
    url = make_url(settings.database_url)
    if not url.database or not url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL 必须以 _test 结尾，禁止重建其他数据库")
    try:
        admin = create_async_engine(
            url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
        )
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        await admin.dispose()
    except Exception as error:
        pytest.skip(
            f"连接不到测试数据库（{type(error).__name__}），跳过接口测试。"
            "请先启动数据库：docker compose up -d db"
        )

    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return settings


@pytest.fixture
async def app(test_settings):
    application = create_app(
        settings=test_settings.model_copy(deep=True), mail_sender=MemoryMailSender()
    )
    async with application.state.engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE users, sessions, email_tokens, hot_topics, hot_collection_runs CASCADE")
        )
    yield application
    await application.state.ai_hub.close()
    await application.state.engine.dispose()


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.fixture
async def client(app):
    async with _client(app) as c:
        yield c


@pytest.fixture
async def other_client(app):
    """模拟另一台设备。"""
    async with _client(app) as c:
        yield c


@pytest.fixture
def outbox(app) -> list:
    return app.state.mail_sender.outbox


@pytest.fixture
async def db(app):
    async with app.state.session_factory() as session:
        yield session
