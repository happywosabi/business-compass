from uuid import uuid4

import pytest

from app.db.models import AIRun
from tests.engine.test_orchard import orchard_data

from .helpers import login, register, verify

pytestmark = pytest.mark.anyio


async def test_orchard_lifecycle_isolation_revision_and_snapshot(client, other_client):
    await register(client)
    await login(client)
    templates = (await client.get("/api/templates")).json()
    assert [t["key"] for t in templates] == ["physical_store", "orchard"]
    assert len(templates[1]["quick_required_keys"]) == 5
    response = await client.post(
        "/api/profiles",
        json={
            "name": "测试果园",
            "city": "梅州",
            "template_key": "orchard",
            "parameters": orchard_data(),
        },
    )
    assert response.status_code == 201, response.text
    profile = response.json()
    assert profile["quick_missing"] == []
    assert profile["stage"] == "operating"
    path = f"/api/profiles/{profile['id']}"
    snapshot_response = await client.post(path + "/evaluations", json={"revision": 1})
    assert snapshot_response.status_code == 201, snapshot_response.text
    snapshot = snapshot_response.json()
    assert snapshot["results"]["scenarios"]["base"]["labor_adjusted_earnings"] == 5200
    same = await client.post(path + "/evaluations", json={"revision": 2})
    assert same.json()["id"] == snapshot["id"]
    await client.patch(
        path + "/parameters", json={"revision": 2, "changes": {"orchard.unpaid_labor": 10000}}
    )
    assert (
        await client.patch(
            path + "/parameters", json={"revision": 2, "changes": {"orchard.unpaid_labor": 0}}
        )
    ).status_code == 409
    assert (
        await client.patch(
            path + "/parameters", json={"revision": 3, "changes": {"revenue.avg_ticket": 5}}
        )
    ).status_code == 422
    body = {
        "revision": 3,
        "evaluation_id": snapshot["id"],
        "changes": {
            "orchard.shared_costs": {
                "base": {
                    "land_rent": {"base": 5000},
                    "maintenance": {"base": 0},
                    "other": {"base": 0},
                }
            }
        },
    }
    trial = await client.post(path + "/what-if", json=body)
    assert trial.status_code == 200, trial.text
    assert trial.json()["surplus_delta"] == 5000
    assert (await client.get(path)).json()["revision"] == 3
    applied = await client.post(path + "/what-if/apply", json=body)
    assert applied.status_code == 201, applied.text
    assert applied.json()["results"]["scenarios"]["base"]["labor_adjusted_earnings"] == 10200
    assert (await client.get(path + f"/evaluations/{snapshot['id']}")).json() == snapshot
    copied = (
        await client.post(path + "/copy", json={"revision": applied.json()["profile_revision"]})
    ).json()
    assert copied["template_key"] == "orchard"
    assert copied["parameters"] == applied.json()["parameters"]
    await client.delete(f"/api/profiles/{copied['id']}?revision=1")
    restored = await client.post(f"/api/profiles/{copied['id']}/restore", json={"revision": 2})
    assert restored.status_code == 200
    await register(other_client, "other@example.com")
    await login(other_client, "other@example.com")
    assert (await other_client.get(path)).status_code == 404
    assert (await other_client.get(path + f"/evaluations/{snapshot['id']}")).status_code == 404


async def test_draft_missing_and_template_mismatch(client):
    await register(client)
    await login(client)
    draft = await client.post(
        "/api/profiles", json={"name": "空果园", "city": "梅州", "template_key": "orchard"}
    )
    assert draft.status_code == 201, draft.text
    assert len(draft.json()["quick_missing"]) == 5
    assert (
        await client.post(f"/api/profiles/{draft.json()['id']}/evaluations", json={"revision": 1})
    ).status_code == 422
    bad = await client.post(
        "/api/profiles",
        json={
            "name": "错模板",
            "city": "梅州",
            "template_key": "orchard",
            "parameters": {"revenue": {"daily_orders": {"base": 10}}},
        },
    )
    assert bad.status_code == 422


async def test_orchard_marketing_only_public_facts(client, app, outbox, db):
    await register(client)
    await login(client)
    await verify(client, outbox)
    data = orchard_data()
    data["orchard"]["supply"] = {
        "base": {"pack_net_kg": 5, "minimum_order": "20箱", "specification": "红心蜜柚"}
    }
    profile = (
        await client.post(
            "/api/profiles",
            json={"name": "果园", "city": "梅州", "template_key": "orchard", "parameters": data},
        )
    ).json()
    path = f"/api/profiles/{profile['id']}/content"
    topics = (await client.get(path + "/topics")).json()
    assert all(t["kind"] == "orchard" for t in topics)
    # 不启动外部模型；核对实际排队素材。
    app.state.ai_hub.start = lambda run_id, coro: coro.close()
    result = await client.post(
        path + "/drafts",
        json={
            "request_id": str(uuid4()),
            "platform": "xiaohongshu",
            "topic_id": "orchard:supply",
            "audience": "buyers",
        },
    )
    assert result.status_code == 200, result.text
    from sqlalchemy import select

    run = await db.scalar(select(AIRun).where(AIRun.kind == "content"))
    assert run.input["audience"] == "buyers"
    assert run.input["store"]["supply"]["minimum_order"] == "20箱"
    text = str(run.input)
    assert "20000" not in text and "8000" not in text and "shared_costs" not in text


async def test_orchard_report_resume_reuse_and_numeric_verification(client, app, outbox):
    import asyncio

    from .test_interview import FakeLLM

    await register(client)
    await login(client)
    await verify(client, outbox)
    data = orchard_data()
    data["orchard"]["equipment"] = None
    profile = (
        await client.post(
            "/api/profiles",
            json={
                "name": "报告果园",
                "city": "梅州",
                "template_key": "orchard",
                "parameters": data,
            },
        )
    ).json()
    path = f"/api/profiles/{profile['id']}"
    snapshot = (await client.post(path + "/evaluations", json={"revision": 1})).json()
    app.state.llm = FakeLLM(
        [
            {
                "role": "assistant",
                "content": "本期收入43200元，经营结余13200元，扣家庭劳动估值后5200元。保本均价4.17元/kg。假定销售款全部收齐，需核实产量、销路与成本。",
            }
        ]
    )
    report_path = path + f"/evaluations/{snapshot['id']}/report"
    response = await client.post(report_path, json={"request_id": str(uuid4())})
    assert response.status_code == 200
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    saved = (await client.get(report_path)).json()
    assert saved["status"] == "succeeded", saved
    assert "13200元" in saved["content"]
    assert (await client.post(report_path, json={"request_id": str(uuid4())})).json()[
        "status"
    ] == "succeeded"
    assert len(app.state.llm.calls) == 1
    assert (await client.get(report_path)).json()["content"] == saved["content"]


async def test_orchard_interview_and_clear_guard(client, app, outbox):
    from .test_interview import FakeLLM, tool

    await register(client)
    await login(client)
    await verify(client, outbox)
    profile = (
        await client.post(
            "/api/profiles",
            json={
                "name": "访谈果园",
                "city": "梅州",
                "template_key": "orchard",
                "parameters": orchard_data(),
            },
        )
    ).json()
    path = f"/api/profiles/{profile['id']}"
    app.state.llm = FakeLLM(
        [
            tool("update_parameters", {"changes": {"orchard.varieties": None}, "reason": "占位"}),
            {"role": "assistant", "content": "工作天数需要确认，原来的品种数据保留。"},
        ]
    )
    r = await client.post(
        path + "/interview/messages",
        json={
            "revision": 1,
            "request_id": str(uuid4()),
            "content": "两个人每天300，工作天数不知道",
        },
    )
    assert r.status_code == 200
    assert (await client.get(path)).json()["revision"] == 1
    assert (await client.get(path)).json()["parameters"] == profile["parameters"]
    app.state.llm = FakeLLM([])
    r = await client.post(
        path + "/interview/messages",
        json={"revision": 1, "request_id": str(uuid4()), "content": "跑一版吧"},
    )
    assert r.status_code == 200 and "evaluation_id" in r.text
    assert len(app.state.llm.calls) == 0
