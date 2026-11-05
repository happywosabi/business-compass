import pytest
from pydantic import ValidationError
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


@pytest.mark.parametrize(
    "override",
    [
        {"app_base_url": "http://compass.example.com"},
        {"app_base_url": "https://user:pass@compass.example.com"},
        {"session_cookie_secure": False},
        {"postgres_password": "change-me"},
    ],
)
def test_production_rejects_insecure_configuration(override):
    fields = dict(
        app_env="production",
        app_base_url="https://compass.example.com",
        session_cookie_secure=True,
        postgres_password="test-random-password",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(fields | override))


def test_production_accepts_https_and_secure_cookie():
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_base_url="https://compass.example.com",
        session_cookie_secure=True,
        postgres_password="test-random-password",
    )
    assert settings.is_production


def test_app_rejects_unsafe_model_copy_before_creating_resources():
    from app.main import create_app

    settings = Settings(_env_file=None, app_env="test", session_cookie_secure=False)
    with pytest.raises(ValueError, match="HTTPS"):
        create_app(settings.model_copy(update={"app_env": "production"}))
