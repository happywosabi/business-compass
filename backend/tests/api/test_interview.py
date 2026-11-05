import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.db.base import utcnow
from app.db.models import AIRun, Message, ParameterChange, User
from app.llm.reports import verify_numbers

from .helpers import login, register
from .test_profiles import create_profile

pytestmark = pytest.mark.anyio


def tool(name, arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": str(uuid4()),
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def complete(self, messages, tools=None, *, model, on_delta=None, thinking=None):
        self.calls.append(messages.copy())
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if on_delta and reply.get("content"):
            await on_delta(reply["content"])
        return reply, {"prompt_tokens": 10, "completion_tokens": 5}


@pytest.fixture
async def prepared(client, db):
    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    profile = await create_profile(client)
    return profile, f"/api/profiles/{profile['id']}/interview"


async def test_tools_persist_sources_history_usage_and_idempotency(client, app, db, prepared):
    profile, path = prepared
    app.state.llm = FakeLLM(
        [
            tool(
                "update_parameters",
                {
                    "changes": {"revenue.avg_ticket": {"base": 15, "source": "user"}},
                    "reason": "用户说主力15元",
                },
            ),
            {"role": "assistant", "content": "记下了。房租每月大概多少？"},
        ]
    )
    body = {"request_id": str(uuid4()), "revision": 1, "content": "平均每杯15元"}
    response = await client.post(path + "/messages", json=body)
    assert response.status_code == 200
    assert "event: done" in response.text, response.text
    assert "event: delta" in response.text
    p = (await client.get(f"/api/profiles/{profile['id']}")).json()
    assert p["revision"] == 2
    assert p["parameters"]["revenue"]["avg_ticket"]["source"] == "user"
    change = await db.scalar(
        select(ParameterChange).where(ParameterChange.parameter_key == "revenue.avg_ticket")
    )
    assert change.source == "ai_extraction" and change.message_id
    assert await db.get(Message, change.message_id)
    history = (await client.get(path)).json()
    assert len(history["messages"]) == 3
    assert history["runs"][0]["input_tokens"] == 20
    repeated = await client.post(path + "/messages", json=body)
    assert "event: resume" in repeated.text
    assert len(app.state.llm.calls) == 2
    assert (await client.get(f"/api/profiles/{profile['id']}")).json()["revision"] == 2
    assert (
        await client.post(path + "/messages", json={**body, "content": "改了"})
    ).status_code == 409


async def test_invalid_tool_returns_error_then_recovers(client, app, prepared):
    profile, path = prepared
    app.state.llm = FakeLLM(
        [
            tool(
                "update_parameters",
                {
                    "changes": {"fixed_cost.rent": {"base": -1, "source": "default"}},
                    "reason": "估算",
                },
            ),
            tool(
                "update_parameters",
                {
                    "changes": {
                        "fixed_cost.rent": {
                            "base": 12000,
                            "source": "ai_inferred",
                            "note": "仅为暂用估计",
                        }
                    },
                    "reason": "用户要求估算",
                },
            ),
            {"role": "assistant", "content": "已标为估算，签约前再核实。"},
        ]
    )
    response = await client.post(
        path + "/messages",
        json={"request_id": str(uuid4()), "revision": 1, "content": "帮我估房租"},
    )
    assert "event: done" in response.text, response.text
    assert "error" in app.state.llm.calls[1][-1]["content"]
    p = (await client.get(f"/api/profiles/{profile['id']}")).json()
    assert p["revision"] == 2
    assert p["parameters"]["fixed_cost"]["rent"]["source"] == "ai_inferred"


async def test_failed_provider_preserves_saved_data_and_context_pairs(client, app, prepared):
    profile, path = prepared
    app.state.llm = FakeLLM(
        [
            tool("use_default", {"keys": ["revenue.open_days"]}),
            RuntimeError("network failure"),
            {"role": "assistant", "content": "我们继续。"},
        ]
    )
    response = await client.post(
        path + "/messages",
        json={"request_id": str(uuid4()), "revision": 1, "content": "营业天数先用默认值"},
    )
    assert "event: error" in response.text
    p = (await client.get(f"/api/profiles/{profile['id']}")).json()
    assert p["parameters"]["revenue"]["open_days"]["source"] == "default"
    await client.post(
        path + "/messages",
        json={"request_id": str(uuid4()), "revision": p["revision"], "content": "继续"},
    )
    # 失败回合不进入历史上下文，最新档案保留所有已提交数字。
    assert all(m["role"] != "tool" for m in app.state.llm.calls[-1])


async def test_verified_gate_and_every_endpoint_owned(client, app, other_client, prepared):
    profile, path = prepared
    app.state.llm = FakeLLM([{"role": "assistant", "content": "你好"}])
    await client.post(
        path + "/messages", json={"request_id": str(uuid4()), "revision": 1, "content": "开始"}
    )
    run_id = (await client.get(path)).json()["runs"][0]["id"]
    await register(other_client, "other@example.com")
    await login(other_client, "other@example.com")
    assert (
        await other_client.post(
            path + "/messages", json={"request_id": str(uuid4()), "revision": 1, "content": "开始"}
        )
    ).status_code == 403
    for suffix, method in [
        ("", "GET"),
        (f"/runs/{run_id}", "GET"),
        (f"/runs/{run_id}/cancel", "POST"),
    ]:
        assert (await other_client.request(method, path + suffix)).status_code == 404


async def test_daily_quota_atomic_and_cancel(client, app, db, prepared):
    _, path = prepared
    started, release = asyncio.Event(), asyncio.Event()

    class Slow:
        async def complete(self, *args, **kwargs):
            started.set()
            await release.wait()
            return {"role": "assistant", "content": "完成"}, {}

    app.state.llm = Slow()
    app.state.settings.ai_daily_quota = 1
    task = asyncio.create_task(
        client.post(
            path + "/messages", json={"request_id": str(uuid4()), "revision": 1, "content": "开始"}
        )
    )
    await asyncio.wait_for(started.wait(), 5)
    run = await db.scalar(select(AIRun))
    assert (
        await client.post(
            path + "/messages", json={"request_id": str(uuid4()), "revision": 1, "content": "重复"}
        )
    ).status_code == 409
    await client.post(path + f"/runs/{run.id}/cancel")
    release.set()
    await task
    # 完成前再次检查取消，防止迟到的模型响应标记成功。
    assert (
        await client.post(
            path + "/messages", json={"request_id": str(uuid4()), "revision": 1, "content": "再来"}
        )
    ).status_code == 429


async def test_report_retries_and_fails_closed(client, app, db, prepared, milk_tea):
    profile, _ = prepared
    p = (
        await client.patch(
            f"/api/profiles/{profile['id']}/parameters",
            json={
                "revision": 1,
                "changes": {
                    f"{section}.{key}": value
                    for section, entries in milk_tea.model_dump(mode="json").items()
                    if isinstance(entries, dict) and section != "traffic_estimates"
                    for key, value in entries.items()
                    if value is not None
                },
            },
        )
    ).json()
    snapshot = (
        await client.post(
            f"/api/profiles/{profile['id']}/evaluations", json={"revision": p["revision"]}
        )
    ).json()
    app.state.llm = FakeLLM(
        [
            {"role": "assistant", "content": "需要999万元。"},
            {"role": "assistant", "content": "第21个月收回投入，建议准备34万元到38万元。"},
        ]
    )
    path = f"/api/profiles/{profile['id']}/evaluations/{snapshot['id']}/report"
    response = await client.post(path, json={"request_id": str(uuid4())})
    assert response.status_code == 200, response.text
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    report = (await client.get(path)).json()
    assert report["status"] == "succeeded", report
    assert "不构成投资建议" in report["content"]
    assert len(app.state.llm.calls) == 2
    assert (
        await client.get(f"/api/profiles/{profile['id']}/evaluations/{snapshot['id']}")
    ).json() == snapshot


def test_report_units_rounding_and_unknown_numbers():
    allowed = {"元": [341040, -267040], "月": [21], "单": [147]}
    assert verify_numbers("准备34万元。第21个月回本，每天147杯。", allowed)
    assert not verify_numbers("准备34个月", allowed)
    assert not verify_numbers("准备99万元", allowed)
    assert not verify_numbers("1. 可以投入", allowed)
    assert not verify_numbers("准备三十四万元", allowed)
    assert not verify_numbers("安全余量百分之九十", allowed)
    assert not verify_numbers("第二十一个月回本", allowed)
