"""控制真实ASGI请求交错，回归审计中的认证竞争。邮件只使用内存发送器。"""

import asyncio

import pytest
from sqlalchemy import func, select, update

from app.auth import passwords
from app.db.models import EmailToken, User

from .helpers import EMAIL, NEW_PASSWORD, PASSWORD, login, register, token_from

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("action", ["reset", "change"])
async def test_inflight_old_login_cannot_survive_password_change(
    client, other_client, outbox, monkeypatch, action
):
    await register(client)
    await login(client)
    await client.post("/api/auth/forgot-password", json={"email": EMAIL})
    token = token_from(outbox[-1])
    entered, release = asyncio.Event(), asyncio.Event()
    original = passwords.verify_password

    async def pause(hashed, supplied):
        valid = await original(hashed, supplied)
        if not entered.is_set():
            entered.set()
            await release.wait()
        return valid

    monkeypatch.setattr(passwords, "verify_password", pause)
    pending = asyncio.create_task(login(other_client))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        result = (
            await client.post(
                "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
            )
            if action == "reset"
            else await client.post(
                "/api/auth/change-password",
                json={"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            )
        )
        assert result.status_code == 200
    finally:
        release.set()
    assert (await pending).status_code == 401
    assert (await other_client.get("/api/auth/me")).status_code == 401


async def test_concurrent_failures_reach_lock_without_lost_updates(
    client, other_client, db, monkeypatch
):
    await register(client)
    original = passwords.verify_password
    ready, release = asyncio.Event(), asyncio.Event()
    arrived = 0

    async def barrier(hashed, supplied):
        nonlocal arrived
        valid = await original(hashed, supplied)
        arrived += 1
        if arrived == 8:
            ready.set()
        await release.wait()
        return valid

    monkeypatch.setattr(passwords, "verify_password", barrier)
    tasks = [asyncio.create_task(login(other_client, password="bad-password")) for _ in range(8)]
    try:
        await asyncio.wait_for(ready.wait(), 10)
    finally:
        release.set()
    statuses = [r.status_code for r in await asyncio.gather(*tasks)]
    assert statuses.count(401) == 4 and statuses.count(429) == 4
    user = await db.scalar(select(User))
    assert user.locked_until is not None


async def test_change_revokes_old_reset_and_binds_current_session(client, other_client, outbox, db):
    await register(client)
    await login(client)
    await login(other_client)
    await client.post("/api/auth/forgot-password", json={"email": EMAIL})
    token = token_from(outbox[-1])
    assert (
        await client.post(
            "/api/auth/change-password",
            json={"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/auth/reset-password", json={"token": token, "new_password": "Other-new-pass-2030"}
        )
    ).status_code == 400
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await other_client.get("/api/auth/me")).status_code == 401
    # 即使有人漏删旧会话或令牌，版本不匹配也不能消费。
    await db.execute(
        update(EmailToken).where(EmailToken.purpose == "reset_password").values(used_at=None)
    )
    await db.commit()
    assert (
        await client.post(
            "/api/auth/reset-password", json={"token": token, "new_password": "Other-new-pass-2030"}
        )
    ).status_code == 400


@pytest.mark.parametrize(
    "endpoint,purpose",
    [("/forgot-password", "reset_password"), ("/resend-verification", "verify_email")],
)
async def test_email_reservations_are_serialized(client, app, outbox, db, endpoint, purpose):
    await register(client)
    await login(client)
    # 保留注册邮件计次，但让验证重发间隔已过。
    from datetime import timedelta

    from app.db.base import utcnow

    await db.execute(update(EmailToken).values(created_at=utcnow() - timedelta(minutes=2)))
    await db.commit()
    app.state.settings.email_daily_limit = 2
    outbox.clear()
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/auth" + endpoint, json={"email": EMAIL} if purpose == "reset_password" else {}
            )
            for _ in range(8)
        ]
    )
    assert all(r.status_code in (200, 429) for r in responses)
    assert len(outbox) == 1
    active = await db.scalar(
        select(func.count())
        .select_from(EmailToken)
        .where(EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
    )
    assert active == 1


async def test_inflight_change_cannot_overwrite_reset(client, other_client, outbox, monkeypatch):
    await register(client)
    await login(client)
    await client.post("/api/auth/forgot-password", json={"email": EMAIL})
    token = token_from(outbox[-1])
    original = passwords.verify_password
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause(hashed, supplied):
        valid = await original(hashed, supplied)
        entered.set()
        await release.wait()
        return valid

    monkeypatch.setattr(passwords, "verify_password", pause)
    task = asyncio.create_task(
        client.post(
            "/api/auth/change-password",
            json={"old_password": PASSWORD, "new_password": "Different-pass-2030"},
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    try:
        assert (
            await other_client.post(
                "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
            )
        ).status_code == 200
    finally:
        release.set()
    assert (await task).status_code == 401


async def test_concurrent_mail_daily_limit_and_latest_token(client, app, outbox, db):
    await register(client)
    app.state.settings.email_resend_seconds = 0
    app.state.settings.email_daily_limit = 2
    outbox.clear()
    responses = await asyncio.gather(
        *[client.post("/api/auth/forgot-password", json={"email": EMAIL}) for _ in range(8)]
    )
    assert all(r.status_code == 200 for r in responses)
    assert len(outbox) == 2
    tokens = list(
        await db.scalars(select(EmailToken).where(EmailToken.purpose == "reset_password"))
    )
    assert len(tokens) == 2
    assert sum(t.used_at is None for t in tokens) == 1
