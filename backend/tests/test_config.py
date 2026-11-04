from sqlalchemy.engine import make_url

from app.config import Settings
from app.logs import mask_email


def test_database_url_is_built_from_parts():
    settings = Settings(
        _env_file=None,
        postgres_user="bc",
        postgres_password="p@ss:w/rd%",
        postgres_host="db",
        postgres_db="business_compass",
    )
    url = make_url(settings.sqlalchemy_url())
    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "db"
    assert url.password == "p@ss:w/rd%"  # 特殊字符被正确转义和还原
    assert make_url(settings.sqlalchemy_url(database="other")).database == "other"


def test_explicit_database_url_wins():
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://x@/y?host=/tmp")
    assert settings.sqlalchemy_url() == "postgresql+asyncpg://x@/y?host=/tmp"
    # 指定库名时仍按各项拼出（用于测试库）
    assert make_url(settings.sqlalchemy_url(database="y_test")).database == "y_test"


def test_secrets_are_hidden_in_repr():
    settings = Settings(_env_file=None, smtp_password="top-secret", deepseek_api_key="sk-123")
    assert "top-secret" not in repr(settings)
    assert "sk-123" not in repr(settings)


def test_mask_email():
    assert mask_email("chestnut@example.com") == "c***@example.com"
    assert mask_email("broken") == "***"
