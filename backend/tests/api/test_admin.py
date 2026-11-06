"""后台权限、会话失效、并发控制、隐私和审计回归。"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.admin.cli import set_admin
from app.db.base import utcnow
from app.db.models import AdminAudit, AIRun, Conversation, HotTopic, Message, User, UserSession
from tests.api.helpers import login, register
from tests.api.test_profiles import create_profile

pytestmark = pytest.mark.anyio
HEADERS = {"Origin": "http://testserver"}


@pytest.fixture
async def admin(client, db):
    await register(client)
    await db.execute(update(User).values(email_verified_at=utcnow(), is_admin=True))
    await db.commit()
    await login(client)
    return await db.scalar(select(User))


async def unlock(client):
    from tests.api.helpers import PASSWORD

    response = await client.post("/api/admin/unlock", json={"password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response


async def test_gate_origin_cache_and_no_public_privilege(client, db):
    response = await client.get("/api/admin/overview")
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    await register(client)
    await login(client)
    for path in [
        "session",
        "overview",
        "users",
        "runs",
        "profiles",
        "hotspots",
        "audits",
        "system",
    ]:
        response = await client.get("/api/admin/" + path)
        assert response.status_code == 403
    assert (await client.post("/api/admin/unlock", json={"password": "x"})).status_code == 403
    assert (
        await client.post(
            "/api/admin/unlock", json={"password": "x"}, headers={"Origin": "https://evil.test"}
        )
    ).status_code == 403


async def test_unlock_expiry_password_change_and_failure_lock(client, db, admin, app):
    assert (await client.get("/api/admin/overview")).status_code == 423
    result = await unlock(client)
    assert 890 < (datetime_value(result.json()["expires_at"]) - utcnow()).total_seconds() <= 900
    assert (await client.get("/api/admin/overview")).status_code == 200
    await db.execute(update(UserSession).values(admin_until=utcnow() - timedelta(seconds=1)))
    await db.commit()
    assert (await client.get("/api/admin/overview")).status_code == 423
    for _ in range(app.state.settings.login_max_failures):
        await client.post("/api/admin/unlock", json={"password": "bad-password"}, headers=HEADERS)
    assert (
        await client.post("/api/admin/unlock", json={"password": "bad-password"}, headers=HEADERS)
    ).status_code == 429
    await db.execute(update(User).values(locked_until=None))
    await db.commit()
    await unlock(client)
    from tests.api.helpers import PASSWORD

    response = await client.post(
        "/api/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "DifferentSafe!8472"},
    )
    assert response.status_code == 200
    assert (await client.get("/api/admin/overview")).status_code == 423


def datetime_value(value):
    from datetime import datetime

    return datetime.fromisoformat(value)


async def test_user_actions_optimistic_and_audit_atomic(client, other_client, db, admin):
    await unlock(client)
    await register(other_client, "target@example.com")
    await login(other_client, "target@example.com")
    users = (await client.get("/api/admin/users?q=target")).json()["items"]
    target = users[0]
    expected = {
        k: target[k]
        for k in ["status", "daily_ai_quota", "is_admin", "failed_login_count", "locked_until"]
    }
    path = f"/api/admin/users/{target['id']}/actions"
    body = {"action": "quota", "expected": expected, "quota": 0, "reason": "核对用户额度限制"}
    response = await client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["state"]["daily_ai_quota"] == 0
    assert (await client.post(path, json=body, headers=HEADERS)).status_code == 409
    body.update(action="disable", expected=response.json()["state"])
    assert (await client.post(path, json=body, headers=HEADERS)).status_code == 200
    assert (await other_client.get("/api/auth/me")).status_code == 401
    audits = list(
        await db.scalars(
            select(AdminAudit).where(AdminAudit.action.in_(["user.quota", "user.disable"]))
        )
    )
    assert len(audits) == 2 and audits[0].changes["after"]["daily_ai_quota"] == 0
    assert (
        await client.post(path, json={**body, "quota": 1001}, headers=HEADERS)
    ).status_code == 422


async def test_cli_verification_last_admin_and_revocation(client, other_client, db, admin):
    admin_email = admin.email
    with pytest.raises(ValueError, match="保留"):
        await set_admin(db, admin_email, False, "测试撤销最后管理员")
    await db.rollback()
    await register(other_client, "second@example.com")
    with pytest.raises(ValueError, match="验证"):
        await set_admin(db, "second@example.com", True, "测试已验证邮箱限制")
    await db.rollback()
    await db.execute(
        update(User).where(User.email == "second@example.com").values(email_verified_at=utcnow())
    )
    await db.commit()
    await set_admin(db, "second@example.com", True, "指定第二个管理账号")
    await unlock(client)
    await set_admin(db, admin_email, False, "撤销原管理员的权限")
    assert (await client.get("/api/admin/overview")).status_code == 401


async def test_read_diagnostics_redact_internal_protocol(client, db, admin):
    await unlock(client)
    profile = await create_profile(client)
    uid, pid = admin.id, UUID(profile["id"])
    run = AIRun(
        user_id=uid,
        profile_id=pid,
        request_id=uuid4(),
        kind="interview",
        status="succeeded",
        model="fake",
        input={"secret": "RAW_INPUT"},
        output={"secret": "RAW_OUTPUT"},
        error="SECRET_ERROR",
        lease_until=utcnow(),
    )
    db.add(run)
    conv = Conversation(profile_id=pid)
    db.add(conv)
    await db.flush()
    for i, payload in enumerate(
        [
            {"role": "system", "content": "SECRET_SYSTEM"},
            {"role": "user", "content": "正常用户问题"},
            {"role": "assistant", "content": "正常回复", "reasoning_content": "SECRET_REASONING"},
            {"role": "assistant", "content": "SECRET_TOOL_BODY", "tool_calls": []},
            {"role": "tool", "content": "SECRET_TOOL_RESULT", "tool_call_id": "x"},
        ]
    ):
        db.add(
            Message(
                conversation_id=conv.id,
                run_id=run.id,
                ordinal=i,
                payload=payload,
                prompt_version="v",
            )
        )
    await db.commit()
    response = await client.get("/api/admin/runs")
    assert response.status_code == 200
    assert not any(x in response.text for x in ["RAW_INPUT", "RAW_OUTPUT", "SECRET_ERROR"])
    response = await client.post(
        f"/api/admin/profiles/{pid}/inspect",
        json={"section": "chat", "reason": "帮助用户排查对话错误"},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert "正常回复" in response.text and "正常用户问题" in response.text
    assert "SECRET_" not in response.text
    assert (
        await db.scalar(
            select(func.count())
            .select_from(AdminAudit)
            .where(AdminAudit.action == "profile.read.chat")
        )
        == 1
    )
    for section in ["parameters", "history", "evaluations", "reports", "copy"]:
        assert (
            await client.post(
                f"/api/admin/profiles/{pid}/inspect",
                json={"section": section, "reason": "协助用户检查资料问题"},
                headers=HEADERS,
            )
        ).status_code == 200
    for path in ["users", "runs", "profiles", "hotspots", "audits"]:
        assert (await client.get(f"/api/admin/{path}?limit=101")).status_code == 422
        assert (await client.get(f"/api/admin/{path}?cursor=broken")).status_code == 422


async def test_hotspot_hidden_survives_automatic_refresh(client, db, admin):
    await unlock(client)
    row = HotTopic(
        fingerprint="test",
        title="水果供货",
        url="https://example.com",
        channel="news",
        rank=1,
        safe=True,
    )
    db.add(row)
    await db.commit()
    response = await client.post(
        f"/api/admin/hotspots/{row.id}/visibility",
        json={"hidden": True, "expected": False, "reason": "信息真实性需要进一步核实"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    await db.execute(update(HotTopic).values(safe=True, fetched_at=utcnow()))
    await db.commit()
    from app.content.hot import recommendations

    assert await recommendations(db, industry="fruit_retail") == []
    assert (await client.get("/api/admin/system")).status_code == 200


async def test_disabling_account_prevents_inflight_content_commit(
    client, other_client, app, db, admin
):
    import asyncio

    await unlock(client)
    await register(other_client, "target@example.com")
    await login(other_client, "target@example.com")
    await db.execute(
        update(User).where(User.email == "target@example.com").values(email_verified_at=utcnow())
    )
    await db.commit()
    profile = await create_profile(other_client)
    started, released = asyncio.Event(), asyncio.Event()

    class Slow:
        async def complete(self, *args, **kwargs):
            started.set()
            await released.wait()
            return {"role": "assistant", "content": "这份文案不应保存"}, {
                "prompt_tokens": 10,
                "completion_tokens": 10,
            }

    app.state.llm = Slow()
    response = await other_client.post(
        f"/api/profiles/{profile['id']}/content/drafts",
        json={"request_id": str(uuid4()), "topic_id": "evergreen:process", "platform": "moments"},
    )
    assert response.status_code == 200
    await started.wait()
    target = (await client.get("/api/admin/users?q=target")).json()["items"][0]
    expected = {
        k: target[k]
        for k in ["status", "daily_ai_quota", "is_admin", "failed_login_count", "locked_until"]
    }
    response = await client.post(
        f"/api/admin/users/{target['id']}/actions",
        json={"action": "disable", "expected": expected, "reason": "核实异常账号并停止生成"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    released.set()
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    from app.db.models import ContentDraft

    draft = await db.scalar(
        select(ContentDraft).where(ContentDraft.profile_id == UUID(profile["id"]))
    )
    run = await db.get(AIRun, draft.run_id)
    assert run.status == "cancelled" and draft.content is None


async def test_admin_operations_do_not_share_public_collection_lock(client, db, admin):
    from sqlalchemy import text

    await db.execute(text("SELECT pg_advisory_xact_lock(9412272)"))
    response = await unlock(client)
    assert response.status_code == 200
    await db.rollback()
