"""注册、验证邮箱、重新发送验证邮件。"""

import pytest

from app.auth.dependencies import VerifiedUser

from .helpers import (
    EMAIL,
    PASSWORD,
    backdate_email_tokens,
    expire_email_tokens,
    get_user,
    login,
    register,
    token_from,
    verify,
)

pytestmark = pytest.mark.anyio


async def test_register_sends_verification_email(client, outbox, db):
    response = await register(client)
    assert response.status_code == 201

    assert len(outbox) == 1
    mail = outbox[0]
    assert mail.to == EMAIL
    assert "验证" in mail.subject
    assert "http://testserver/verify-email?token=" in mail.text
    assert mail.html and token_from(mail) in mail.html

    user = await get_user(db)
    assert user.email_verified_at is None
    assert user.password_hash.startswith("$argon2id$")  # 不存密码原文
    assert PASSWORD not in user.password_hash


async def test_email_is_stored_in_lowercase(client, db):
    assert (await register(client, email="User@Example.COM")).status_code == 201
    assert (await get_user(db, "user@example.com")) is not None


async def test_duplicate_email_is_rejected(client, outbox):
    await register(client)
    response = await register(client, email="USER@example.com")
    assert response.status_code == 409
    assert "已注册" in response.json()["detail"]
    assert len(outbox) == 1


async def test_disposable_email_is_rejected(client, outbox):
    response = await register(client, email="someone@mailinator.com")
    assert response.status_code == 400
    assert "临时邮箱" in response.json()["detail"]
    assert outbox == []


@pytest.mark.parametrize(
    ("email", "password", "reason"),
    [
        (EMAIL, "abc123", "至少需要 8 位"),
        (EMAIL, "12345678", "太常见"),
        (EMAIL, "Password123", "太常见"),
        (EMAIL, "aaaaaaaaaa", "太常见"),
        ("chestnut2026@example.com", "chestnut2026", "不能和邮箱相同"),
    ],
)
async def test_weak_password_is_rejected(client, email, password, reason):
    response = await register(client, email=email, password=password)
    assert response.status_code == 400
    assert reason in response.json()["detail"]


async def test_invalid_email_format(client):
    assert (await register(client, email="not-an-email")).status_code == 422


async def test_verify_email(client, outbox, db):
    await register(client)
    response = await verify(client, outbox)
    assert response.status_code == 200
    assert (await get_user(db)).email_verified_at is not None

    await login(client)
    assert (await client.get("/api/auth/me")).json()["email_verified"] is True


async def test_verification_link_works_only_once(client, outbox):
    await register(client)
    assert (await verify(client, outbox)).status_code == 200
    assert (await verify(client, outbox)).status_code == 400


async def test_expired_verification_link(client, outbox, db):
    await register(client)
    await expire_email_tokens(db)
    response = await verify(client, outbox)
    assert response.status_code == 400
    assert "过期" in response.json()["detail"]


async def test_unknown_token(client):
    response = await client.post("/api/auth/verify-email", json={"token": "x" * 43})
    assert response.status_code == 400


async def test_resend_requires_login(client):
    assert (await client.post("/api/auth/resend-verification")).status_code == 401


async def test_resend_is_throttled_then_replaces_old_link(client, outbox, db):
    await register(client)
    await login(client)

    # 刚注册时已发过一封，60 秒内不能再发
    response = await client.post("/api/auth/resend-verification")
    assert response.status_code == 429
    assert len(outbox) == 1

    await backdate_email_tokens(db)
    assert (await client.post("/api/auth/resend-verification")).status_code == 200
    assert len(outbox) == 2

    # 旧链接作废，只有最新的链接有效
    old_token = token_from(outbox[0])
    old = await client.post("/api/auth/verify-email", json={"token": old_token})
    assert old.status_code == 400
    assert (await verify(client, outbox)).status_code == 200


async def test_resend_daily_limit(client, outbox, db):
    await register(client)
    await login(client)
    # 注册时 1 封 + 再发 9 封 = 10 封，达到每日上限
    for _ in range(9):
        await backdate_email_tokens(db)
        assert (await client.post("/api/auth/resend-verification")).status_code == 200
    await backdate_email_tokens(db)
    assert (await client.post("/api/auth/resend-verification")).status_code == 429
    assert len(outbox) == 10


async def test_resend_after_verified(client, outbox):
    await register(client)
    await verify(client, outbox)
    await login(client)
    response = await client.post("/api/auth/resend-verification")
    assert response.status_code == 400


async def test_unverified_user_can_log_in_but_not_use_verified_features(app, client, outbox):
    @app.get("/api/test/verified-only")
    async def verified_only(user: VerifiedUser):
        return {"ok": True}

    assert (await client.get("/api/test/verified-only")).status_code == 401

    await register(client)
    assert (await login(client)).status_code == 200
    response = await client.get("/api/test/verified-only")
    assert response.status_code == 403
    assert "验证邮箱" in response.json()["detail"]

    await verify(client, outbox)
    assert (await client.get("/api/test/verified-only")).status_code == 200
