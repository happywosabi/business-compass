"""忘记密码、重置密码、修改密码。"""

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.db.base import utcnow
from app.db.models import User

from .helpers import (
    EMAIL,
    NEW_PASSWORD,
    PASSWORD,
    backdate_email_tokens,
    expire_email_tokens,
    get_user,
    login,
    register,
    token_from,
)

pytestmark = pytest.mark.anyio

GENERIC = "如果该邮箱已注册，我们已发送重置密码的邮件，请查收"


async def forgot(client, email=EMAIL):
    return await client.post("/api/auth/forgot-password", json={"email": email})


async def reset(client, token, password=NEW_PASSWORD):
    return await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": password}
    )


@pytest.fixture
async def user(client, outbox):
    await register(client)
    outbox.clear()


async def test_forgot_password_same_reply_for_unknown_email(client, outbox):
    response = await forgot(client, "nobody@example.com")
    assert response.status_code == 200
    assert response.json()["message"] == GENERIC
    assert outbox == []


async def test_forgot_password_sends_reset_link(client, outbox, user):
    response = await forgot(client)
    assert response.status_code == 200
    assert response.json()["message"] == GENERIC
    assert len(outbox) == 1
    assert "重置密码" in outbox[0].subject
    assert "http://testserver/reset-password?token=" in outbox[0].text


async def test_forgot_password_is_throttled_silently(client, outbox, user):
    await forgot(client)
    second = await forgot(client)
    assert second.status_code == 200  # 回复不变，但不会再发邮件
    assert len(outbox) == 1


async def test_reset_password(client, other_client, outbox, user):
    await login(other_client)
    await forgot(client)
    token = token_from(outbox[0])

    response = await reset(client, token)
    assert response.status_code == 200

    assert (await login(client, password=PASSWORD)).status_code == 401
    assert (await login(client, password=NEW_PASSWORD)).status_code == 200
    # 重置后所有设备退出登录
    assert (await other_client.get("/api/auth/me")).status_code == 401
    # 链接只能用一次
    assert (await reset(client, token, "another-pass-99")).status_code == 400


async def test_weak_new_password_keeps_link_usable(client, outbox, user):
    await forgot(client)
    token = token_from(outbox[0])
    weak = await reset(client, token, "12345678")
    assert weak.status_code == 400
    assert (await reset(client, token)).status_code == 200


async def test_reset_also_verifies_email_and_unlocks(client, outbox, user, db):
    await db.execute(update(User).values(locked_until=utcnow() + timedelta(minutes=10)))
    await db.commit()
    await forgot(client)
    await reset(client, token_from(outbox[0]))

    user_row = await get_user(db)
    assert user_row.email_verified_at is not None
    assert user_row.locked_until is None
    assert (await login(client, password=NEW_PASSWORD)).status_code == 200


async def test_expired_reset_link(client, outbox, user, db):
    await forgot(client)
    await expire_email_tokens(db)
    assert (await reset(client, token_from(outbox[0]))).status_code == 400


async def test_only_latest_reset_link_works(client, outbox, user, db):
    await forgot(client)
    await backdate_email_tokens(db)
    await forgot(client)
    assert len(outbox) == 2
    assert (await reset(client, token_from(outbox[0]))).status_code == 400
    assert (await reset(client, token_from(outbox[1]))).status_code == 200


async def test_verification_link_cannot_reset_password(client, outbox):
    await register(client)
    verification_token = token_from(outbox[0])
    assert (await reset(client, verification_token)).status_code == 400


async def change(client, old=PASSWORD, new=NEW_PASSWORD):
    return await client.post(
        "/api/auth/change-password", json={"old_password": old, "new_password": new}
    )


async def test_change_password_requires_login(client):
    assert (await change(client)).status_code == 401


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        ("wrong-old-password", NEW_PASSWORD, "原密码错误"),
        (PASSWORD, PASSWORD, "不能和原密码相同"),
        (PASSWORD, "12345678", "太常见"),
    ],
)
async def test_change_password_errors(client, user, old, new, reason):
    await login(client)
    response = await change(client, old, new)
    assert response.status_code == 400
    assert reason in response.json()["detail"]


async def test_change_password(client, other_client, user):
    await login(client)
    await login(other_client)
    assert (await change(client)).status_code == 200

    # 当前设备保持登录，其他设备退出
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await other_client.get("/api/auth/me")).status_code == 401
    assert (await login(other_client, password=NEW_PASSWORD)).status_code == 200
