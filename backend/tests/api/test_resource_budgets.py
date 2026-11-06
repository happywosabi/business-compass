"""配额原子性、字节计量、完整轮次裁剪和确认卡片的回归。"""

import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update

from app.confirmations import propose
from app.db.base import utcnow
from app.db.models import (
    AIInputReservation,
    Evaluation,
    PendingAction,
    Profile,
    ResourceUsage,
    User,
)
from app.llm.budget import AccountProvider, fit_messages
from app.resources import json_size
from tests.api.helpers import login, register
from tests.api.test_profiles import create_profile

pytestmark = pytest.mark.anyio


@pytest.fixture
async def owner(client, db):
    await register(client)
    await login(client)
    return await db.scalar(select(User))


async def test_profile_limit_atomic_deleted_count_and_deletion_release(client, db, owner):
    for _ in range(9):
        await create_profile(client)
    responses = await asyncio.gather(
        *[client.post("/api/profiles", json={"name": "并发测试", "city": "杭州"}) for _ in range(3)]
    )
    assert sorted(r.status_code for r in responses) == [201, 429, 429]
    usage = await db.get(ResourceUsage, owner.id)
    assert usage.profile_count == 10
    saved = usage.storage_bytes
    profile = await db.scalar(select(Profile).limit(1))
    path = f"/api/profiles/{profile.id}"
    response = await client.delete(path + f"?revision={profile.revision}")
    assert response.status_code == 204, response.text
    assert (
        await client.post("/api/profiles", json={"name": "仍然计入", "city": "杭州"})
    ).status_code == 429
    await db.execute(delete(Profile).where(Profile.id == profile.id))
    await db.commit()
    await db.refresh(usage)
    assert usage.profile_count == 9 and usage.storage_bytes < saved
    await create_profile(client)


async def test_storage_blocks_growth_allows_shrink_and_existing_reads(client, db, owner):
    profile = await create_profile(client)
    uid = owner.id
    await db.execute(
        update(ResourceUsage)
        .where(ResourceUsage.user_id == uid)
        .values(storage_bytes=11 * 1024 * 1024)
    )
    await db.commit()
    path = f"/api/profiles/{profile['id']}"
    assert (await client.get(path)).status_code == 200
    response = await client.patch(
        path, json={"revision": 1, "value_proposition": {"why": "新增正文"}}
    )
    assert response.status_code == 429
    assert (await client.patch(path, json={"revision": 1, "name": "小店"})).status_code == 200
    assert (
        await client.post("/api/profiles", json={"name": "新档案", "city": "杭州"})
    ).status_code == 429


async def test_write_rate_bounds_and_summary_pagination(client, app, db, owner):
    app.state.settings.profile_writes_per_minute = 3
    for _ in range(3):
        await create_profile(client)
    assert (
        await client.post("/api/profiles", json={"name": "超频", "city": "杭州"})
    ).status_code == 429
    response = await client.get("/api/profiles?limit=2")
    items = response.json()["items"]
    assert len(items) == 2 and "parameters" not in items[0]
    next_page = (
        await client.get(
            "/api/profiles", params={"limit": 2, "cursor": response.json()["next_cursor"]}
        )
    ).json()
    assert len(next_page["items"]) == 1
    assert {i["id"] for i in items}.isdisjoint({i["id"] for i in next_page["items"]})
    assert (await client.get("/api/profiles?cursor=%%%%")).status_code == 422
    assert (
        await client.patch(
            f"/api/profiles/{items[0]['id']}",
            json={"revision": 1, "value_proposition": {"note": "x" * 1001}},
        )
    ).status_code == 422


async def test_input_retries_charged_and_daily_budget_atomic(app, db, owner):
    settings = app.state.settings
    settings.ai_input_daily_bytes = 1024

    class Retry:
        async def complete(self, messages, tools=None, **kwargs):
            await kwargs["before_retry"]()
            return {"role": "assistant", "content": "已收到"}, {}

    provider = AccountProvider(Retry(), app.state.session_factory, settings, owner.id)
    messages = [{"role": "user", "content": "中文的字节计量"}]
    await provider.complete(messages, model="fake")
    count = await db.scalar(
        select(func.sum(AIInputReservation.size)).where(AIInputReservation.user_id == owner.id)
    )
    assert count == json_size({"messages": messages, "tools": None}) * 2
    settings.ai_input_daily_bytes = count + json_size({"messages": messages, "tools": None})
    with pytest.raises(HTTPException) as error:
        await provider.complete(messages, model="fake")
    assert error.value.status_code == 429


def test_trim_keeps_state_current_turn_and_complete_tool_pairs():
    messages = [
        {"role": "system", "content": "规则"},
        {"role": "user", "content": "旧资料" * 1000},
        {"role": "assistant", "tool_calls": [{"id": "t"}]},
        {"role": "tool", "tool_call_id": "t", "content": "结果"},
        {"role": "system", "content": "当前档案必须保留"},
        {"role": "user", "content": "当前问题"},
        {"role": "assistant", "tool_calls": [{"id": "new"}]},
        {"role": "tool", "tool_call_id": "new", "content": "当前结果"},
    ]
    fitted = fit_messages(messages, None, 1024)
    assert [m.get("content") for m in fitted if m["role"] == "system"] == [
        "规则",
        "当前档案必须保留",
    ]
    assert [m.get("tool_call_id") for m in fitted if m["role"] == "tool"] == ["new"]
    with pytest.raises(HTTPException):
        fit_messages(
            [{"role": "system", "content": "必需" * 1000}, {"role": "user", "content": "问题"}],
            None,
            1024,
        )


async def test_confirmation_stale_expired_owned_and_idempotent_defaults(
    client, other_client, db, owner
):
    profile = await create_profile(client)
    row = await db.get(Profile, UUID(profile["id"]))
    action = await propose(db, row, "defaults", {"keys": ["revenue.open_days"]})
    await db.commit()
    path = f"/api/profiles/{row.id}/confirmations/{action['id']}/confirm"
    assert (await client.get(f"/api/profiles/{row.id}")).json()["revision"] == 1
    await register(other_client, "other@example.com")
    await login(other_client, "other@example.com")
    assert (await other_client.post(path, json={"revision": 1})).status_code == 404
    response = await client.post(path, json={"revision": 1})
    assert response.status_code == 200, response.text
    assert (await client.post(path, json={"revision": 1})).json() == response.json()
    await db.refresh(row)
    action = await propose(db, row, "evaluation")
    await db.commit()
    await client.patch(f"/api/profiles/{row.id}", json={"revision": row.revision, "city": "上海"})
    assert (
        await client.post(
            f"/api/profiles/{row.id}/confirmations/{action['id']}/confirm",
            json={"revision": row.revision},
        )
    ).status_code == 409
    await db.refresh(row)
    action = await propose(db, row, "evaluation")
    await db.execute(
        update(PendingAction)
        .where(PendingAction.id == UUID(action["id"]))
        .values(expires_at=utcnow() - timedelta(seconds=1))
    )
    await db.commit()
    assert (
        await client.post(
            f"/api/profiles/{row.id}/confirmations/{action['id']}/confirm",
            json={"revision": row.revision},
        )
    ).status_code == 409
    assert await db.scalar(select(func.count()).select_from(Evaluation)) == 0


async def test_what_if_only_proposes_then_button_applies(client, app, db, owner, milk_tea):
    from uuid import uuid4

    from tests.api.test_interview import FakeLLM, tool

    await db.execute(update(User).where(User.id == owner.id).values(email_verified_at=utcnow()))
    await db.commit()
    profile = await create_profile(client, parameters=milk_tea.model_dump(mode="json"))
    path = f"/api/profiles/{profile['id']}"
    app.state.llm = FakeLLM([tool("what_if", {"changes": {"fixed_cost.rent": 5000}})])
    response = await client.post(
        path + "/interview/messages",
        json={"request_id": str(uuid4()), "revision": 1, "content": "如果房租改成5000元，试算一下"},
    )
    assert "confirmation" in response.text
    assert (await client.get(path)).json()["parameters"]["fixed_cost"]["rent"]["base"] != 5000
    action = (await client.get(path + "/confirmations")).json()[0]
    response = await client.post(
        path + f"/confirmations/{action['id']}/confirm", json={"revision": 1}
    )
    assert response.status_code == 200, response.text
    assert (await client.get(path)).json()["parameters"]["fixed_cost"]["rent"]["base"] == 5000
    assert (
        await client.post(path + f"/confirmations/{action['id']}/confirm", json={"revision": 1})
    ).json() == response.json()
