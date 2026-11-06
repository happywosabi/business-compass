"""应用配置：全部来自环境变量。

- 在 Docker 里：由 compose.yaml 通过 env_file 把项目根目录的 .env 传进容器
- 在本机运行测试时：直接读取项目根目录的 .env
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# backend/app/config.py → 项目根目录/.env（容器里不存在这个文件，会被忽略）
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # ---- 运行环境 ----
    app_env: Literal["development", "production", "test"] = "development"
    app_base_url: str = "http://localhost:8080"  # 邮件里链接的网址前缀

    # ---- 数据库 ----
    # 一般不用直接设置 DATABASE_URL，由下面几项拼出来
    database_url: str | None = None
    postgres_user: str = "business_compass"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "business_compass"
    postgres_host: str = "localhost"  # 容器里由 compose.yaml 改为 db
    postgres_port: int = 5432

    # ---- 登录 ----
    session_cookie_name: str = "bc_session"
    session_cookie_secure: bool = True  # 只通过 HTTPS 发送 Cookie；本机 http 开发时设为 false
    session_days: int = 30
    login_max_failures: int = 5  # 连续失败多少次后锁定
    login_lock_minutes: int = 15
    verify_token_hours: int = 24  # 验证邮箱链接有效期
    reset_token_minutes: int = 60  # 重置密码链接有效期
    email_resend_seconds: int = 60  # 同一类邮件的最短发送间隔
    email_daily_limit: int = 10  # 同一类邮件每个账号每天最多发送次数

    # ---- 邮件 ----
    mail_backend: Literal["smtp", "console"] = "console"
    smtp_host: str = "smtpdm.aliyun.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_timeout_seconds: int = 15
    mail_from: str = ""
    mail_from_name: str = "商业罗盘"

    # ---- 大模型（AI 访谈阶段使用）----
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    interview_model: str = "deepseek-flash"
    report_model: str = "deepseek-v4-pro"
    ai_daily_quota: int = 50
    ai_timeout_seconds: int = 60
    ai_run_seconds: int = 240
    ai_max_output_tokens: int = 3000
    ai_report_max_tokens: int = 8000
    ai_input_max_bytes: int = Field(default=131072, ge=1024)
    ai_input_daily_bytes: int = Field(default=8388608, ge=1024)
    profile_writes_per_minute: int = Field(default=30, ge=1)
    profile_writes_per_day: int = Field(default=300, ge=1)
    calculation_seconds: float = Field(default=5, gt=0, le=30)
    calculation_per_minute: int = Field(default=30, ge=1, le=120)
    calculation_per_day: int = Field(default=300, ge=1)
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "qwen3.7-text-embedding-flash"

    # 默认使用在线行业资讯；可选叠加自部署热点聚合服务
    content_news_enabled: bool = True
    hotapi_base_url: str = ""
    hotapi_channels: str = "weibo,zhihu"
    worker_interval_seconds: int = 7200
    hot_daily_limit: int = Field(default=24, ge=0, le=100)
    hot_min_interval_seconds: int = Field(default=3600, ge=120)
    hot_run_seconds: float = Field(default=90, gt=0, le=240)

    @model_validator(mode="after")
    def production_security(self) -> Settings:
        if self.is_production:
            url = urlsplit(self.app_base_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
            ):
                raise ValueError("生产环境 APP_BASE_URL 必须是无凭据的 HTTPS 地址")
            if not self.session_cookie_secure:
                raise ValueError("生产环境必须设置 SESSION_COOKIE_SECURE=true")
            if not self.database_url and self.postgres_password.get_secret_value() in {
                "",
                "change-me",
            }:
                raise ValueError("生产环境必须配置数据库密码，不能使用模板密码")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def sqlalchemy_url(self, database: str | None = None) -> str:
        """数据库连接地址。传入 database 时连接同一服务器上的另一个库（如测试库）。"""
        if self.database_url and database is None:
            return self.database_url
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=database or self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
