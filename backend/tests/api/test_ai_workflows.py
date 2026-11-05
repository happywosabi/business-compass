"""AI跨页面任务、并发额度和访谈导航回归。"""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.db.models import AIRun, Evaluation, User
from app.interview.service import confirms_evaluation, history_context

from .helpers import login, register
from .test_interview import FakeLLM, tool
from .test_profiles import create_profile

pytestmark = pytest.mark.anyio


@pytest.fixture
async def ready(client, db, milk_tea):
    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=func.now()))
    await db.commit()
    profile = await create_profile(client, parameters=milk_tea.model_dump(mode="json"))
    path = f"/api/profiles/{profile['id']}"
    snapshot = (await client.post(path + "/evaluations", json={"revision": 1})).json()
    return path, snapshot


async def test_three_parallel_tasks_with_report_resume_and_slot_release(client, app, db, ready):
    path, snapshot = ready
    release = asyncio.Event()

    class SlowLLM:
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            await release.wait()
            return {"role": "assistant", "content": "先核实原料报价，再决定是否投入。"}, {}

    app.state.llm = SlowLLM()
    report_path = path + f"/evaluations/{snapshot['id']}/report"
    responses = await asyncio.gather(
        client.post(report_path, json={"request_id": str(uuid4())}),
        *[
            client.post(
                path + "/content/drafts",
                json={
                    "request_id": str(uuid4()),
                    "topic_id": "evergreen:process",
                    "platform": "moments",
                },
            )
            for _ in range(3)
        ],
    )
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 409]
    assert await db.scalar(select(func.count()).select_from(AIRun)) == 3
    # 跨页面重新读取与另一个标签页重新POST均使用同一个报告任务。
    report = (await client.get(report_path)).json()
    assert report["status"] == "running"
    reused = (await client.post(report_path, json={"request_id": str(uuid4())})).json()
    assert reused["id"] == report["run"]["id"]
    assert await db.scalar(select(func.count()).select_from(AIRun)) == 3
    release.set()
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    saved = (await client.get(report_path)).json()
    assert saved["status"] == "succeeded" and saved["content"]
    assert app.state.llm.calls == 3
    # 不改参数从档案重新打开测算，保留同一快照及其已完成报告。
    profile = (await client.get(path)).json()
    again = (
        await client.post(path + "/evaluations", json={"revision": profile["revision"]})
    ).json()
    assert again["id"] == snapshot["id"]
    assert await db.scalar(select(func.count()).select_from(Evaluation)) == 1
    assert (await client.get(report_path)).json()["content"] == saved["content"]
    response = await client.post(
        path + "/content/drafts",
        json={
            "request_id": str(uuid4()),
            "topic_id": "evergreen:process",
            "platform": "moments",
        },
    )
    assert response.status_code == 200
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))


async def test_confirmed_evaluation_finishes_without_extra_model_prose(client, app, db, ready):
    path, _ = ready
    profile = (await client.get(path)).json()
    # 一次模型响应并行返回测算与快捷选项，也必须保留完整工具配对。
    message = tool("run_evaluation", {})
    message["tool_calls"].extend(
        tool("show_quick_replies", {"options": ["继续聊", "手动填写"]})["tool_calls"]
    )
    app.state.llm = FakeLLM([message])
    response = await client.post(
        path + "/interview/messages",
        json={
            "request_id": str(uuid4()),
            "revision": profile["revision"],
            "content": "按刚才确认的数字做个评估给我看看",
        },
    )
    assert "event: done" in response.text and "evaluation_id" in response.text
    assert len(app.state.llm.calls) == 1
    from app.db.models import Conversation

    conv = await db.scalar(
        select(Conversation).where(Conversation.profile_id == UUID(profile["id"]))
    )
    messages = await history_context(db, conv.id)
    calls = [c["id"] for m in messages for c in m.get("tool_calls", [])]
    replies = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
    assert calls == replies
    assert messages[-1]["content"] == "测算已完成，正在打开结果。"


async def test_new_parameters_get_new_snapshot_and_preserve_old_report(client, app, db, ready):
    path, snapshot = ready
    app.state.llm = FakeLLM([{"role": "assistant", "content": "需要先核实报价。"}])
    await client.post(
        path + f"/evaluations/{snapshot['id']}/report", json={"request_id": str(uuid4())}
    )
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    profile = (await client.get(path)).json()
    changed = (
        await client.patch(
            path + "/parameters",
            json={"revision": profile["revision"], "changes": {"fixed_cost.rent": 20000}},
        )
    ).json()
    new = (await client.post(path + "/evaluations", json={"revision": changed["revision"]})).json()
    assert new["id"] != snapshot["id"]
    assert (await client.get(path + f"/evaluations/{new['id']}/report")).json()[
        "status"
    ] == "missing"
    assert (await client.get(path + f"/evaluations/{snapshot['id']}/report")).json()[
        "status"
    ] == "succeeded"


async def test_short_confirmation_runs_calculation_without_another_model_response(
    client, app, ready
):
    path, _ = ready
    app.state.llm = FakeLLM(
        [{"role": "assistant", "content": "关键项齐了，要我现在跑一版测算吗？"}]
    )

    async def send(content):
        profile = (await client.get(path)).json()
        return await client.post(
            path + "/interview/messages",
            json={"request_id": str(uuid4()), "revision": profile["revision"], "content": content},
        )

    await send("数字我都填好了")
    response = await send("跑一版吧")
    assert "event: done" in response.text and "evaluation_id" in response.text
    assert len(app.state.llm.calls) == 1
    # 已完成后再次发明确测算指令，也直接打开同一份结果。
    repeated = await send("跑一版吧")
    assert "evaluation_id" in repeated.text
    assert len(app.state.llm.calls) == 1


def test_short_confirmation_requires_prior_question_and_no_changes():
    assert confirms_evaluation("跑一版吧", "测算已完成，正在打开结果。")
    assert confirms_evaluation("确认", "要我现在跑一版测算吗？")
    assert not confirms_evaluation("可以", "亲戚工资按每月7800元，可以吗？")
    assert not confirms_evaluation("先别算", "要我现在跑一版测算吗？")
    assert not confirms_evaluation("好的，但租金改为5000", "要我现在跑一版测算吗？")
