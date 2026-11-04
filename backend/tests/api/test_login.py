"""登录、会话、退出登录。"""

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.auth.tokens import hash_token
from app.db.base import utcnow
from app.db.models import User, UserSession

from .helpers import EMAIL, PASSWORD, get_user, login, register

pytestmark = pytest.mark.anyio

COOKIE = "bc_session"


@pytest.fixture
async def user(client):
    await register(client)


async def test_login_sets_secure_cookie(client, user, db):
    response = await login(client)
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    assert response.json()["email_verified"] is False

    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Max-Age=2592000" in set_cookie  # 30 天

    # 数据库只存令牌的哈希值
    token = client.cookies[COOKIE]
    session = await db.scalar(select(UserSession))
    assert session.token_hash == hash_token(token)
    assert session.token_hash != token
    assert session.ip == "127.0.0.1"


async def test_me(client, user):
    await login(client)
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_me_requires_login(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


async def test_wrong_password_and_unknown_email_give_same_error(client, user):
    wrong_password = await login(client, password="not-the-password")
    unknown_email = await login(client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "邮箱或密码错误"}


async def test_login_email_is_case_insensitive(client, user):
    assert (await login(client, email="USER@Example.com")).status_code == 200


async def test_lock_after_five_failures(client, user, db):
    for _ in range(4):
        assert (await login(client, password="wrong-password")).status_code == 401
    fifth = await login(client, password="wrong-password")
    assert fifth.status_code == 429
    assert "15 分钟" in fifth.json()["detail"]

    # 锁定期间密码正确也不能登录
    assert (await login(client)).status_code == 429

    # 锁定时间过后可以登录
    await db.execute(update(User).values(locked_until=utcnow() - timedelta(seconds=1)))
    await db.commit()
    assert (await login(client)).status_code == 200
    user_row = await get_user(db)
    assert user_row.failed_login_count == 0
    assert user_row.locked_until is None


async def test_successful_login_resets_failure_count(client, user):
    for _ in range(4):
        await login(client, password="wrong-password")
    assert (await login(client)).status_code == 200
    for _ in range(4):
        assert (await login(client, password="wrong-password")).status_code == 401


async def test_logout(client, user, db):
    await login(client)
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert (
        "Max-Age=0" in response.headers["set-cookie"]
        or "expires=" in response.headers["set-cookie"].lower()
    )
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await db.scalar(select(UserSession))) is None


async def test_logout_without_login(client):
    assert (await client.post("/api/auth/logout")).status_code == 200


async def test_logout_only_affects_current_device(client, other_client, user):
    await login(client)
    await login(other_client)
    await client.post("/api/auth/logout")
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await other_client.get("/api/auth/me")).status_code == 200


async def test_expired_session(client, user, db):
    await login(client)
    await db.execute(update(UserSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    await db.commit()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_disabled_account(client, user, db):
    await login(client)
    await db.execute(update(User).values(status="disabled"))
    await db.commit()
    assert (await client.get("/api/auth/me")).status_code == 401  # 已有会话立即失效
    response = await login(client)
    assert response.status_code == 403
    assert "停用" in response.json()["detail"]


async def test_deleted_account_cannot_log_in(client, user, db):
    await db.execute(update(User).values(deleted_at=utcnow()))
    await db.commit()
    assert (await login(client)).status_code == 401


async def test_last_seen_is_updated_at_most_every_ten_minutes(client, user, db):
    await login(client)
    long_ago = utcnow() - timedelta(minutes=11)
    await db.execute(update(UserSession).values(last_seen_at=long_ago))
    await db.commit()

    await client.get("/api/auth/me")
    db.expire_all()
    first = (await db.scalar(select(UserSession))).last_seen_at
    assert first > long_ago

    await client.get("/api/auth/me")
    db.expire_all()
    assert (await db.scalar(select(UserSession))).last_seen_at == first


async def test_password_is_never_returned(client, user):
    response = await login(client)
    assert PASSWORD not in response.text
    assert "password" not in response.json()
