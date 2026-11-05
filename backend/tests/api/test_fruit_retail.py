from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import AIRun
from app.interview.tools import guard_fruit
from tests.engine.test_fruit_retail import fruit_data

from .helpers import login, register, verify

pytestmark = pytest.mark.anyio


async def test_fruit_lifecycle_and_stage_snapshots(client, other_client):
    await register(client)
    await login(client)
    metadata = (await client.get("/api/templates?industry=fruit_retail")).json()[0]
    assert metadata["key"] == "physical_store"
    assert all(f["key"].startswith("fruit.") for f in metadata["fields"])
    assert metadata["defaults_provisional"] is False
    response = await client.post(
        "/api/profiles",
        json={
            "name": "水果小店",
            "city": "深圳",
            "industry": "fruit_retail",
            "stage": "preparing",
            "parameters": fruit_data(),
        },
    )
    assert response.status_code == 201, response.text
    profile = response.json()
    assert profile["quick_missing"] == []
    path = f"/api/profiles/{profile['id']}"
    snap = await client.post(path + "/evaluations", json={"revision": 1})
    assert snap.status_code == 201, snap.text
    snapshot = snap.json()
    assert snapshot["parameters"]["schema_version"] == 3
    assert snapshot["results"]["scenarios"]["base"]["monthly_procurement"] == pytest.approx(70000)
    assert (await client.post(path + "/evaluations", json={"revision": 2})).json()[
        "id"
    ] == snapshot["id"]
    body = {"revision": 2, "evaluation_id": snapshot["id"], "changes": {"fruit.rent": 3500}}
    preview = await client.post(path + "/what-if", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["surplus_delta"] == pytest.approx(1000)
    assert (await client.get(path)).json()["revision"] == 2
    applied = await client.post(path + "/what-if/apply", json=body)
    assert applied.status_code == 201, applied.text
    revision = applied.json()["profile_revision"]
    assert (await client.get(path + f"/evaluations/{snapshot['id']}")).json() == snapshot
    assert (
        await client.patch(path + "/parameters", json={"revision": 2, "changes": {"fruit.rent": 0}})
    ).status_code == 409
    copied = (await client.post(path + "/copy", json={"revision": revision})).json()
    assert copied["industry"] == "fruit_retail"
    assert (await client.delete(f"/api/profiles/{copied['id']}?revision=1")).status_code == 204
    assert (
        await client.post(f"/api/profiles/{copied['id']}/restore", json={"revision": 2})
    ).status_code == 200
    operating = await client.patch(path, json={"revision": revision, "stage": "operating"})
    assert operating.json()["parameters"]["stage"] == "operating"
    body["revision"] = operating.json()["revision"]
    assert (await client.post(path + "/what-if/apply", json=body)).status_code == 422
    new = (await client.post(path + "/evaluations", json={"revision": body["revision"]})).json()
    assert new["results"]["scenarios"]["base"]["payback_month"] is None
    await register(other_client, "other@example.com")
    await login(other_client, "other@example.com")
    assert (await other_client.get(path)).status_code == 404
    assert (await other_client.get(path + f"/evaluations/{snapshot['id']}")).status_code == 404


async def test_fruit_empty_draft_and_mode_validation(client):
    await register(client)
    await login(client)
    p = (
        await client.post(
            "/api/profiles",
            json={"name": "水果", "city": "深圳", "industry": "fruit_retail", "stage": "operating"},
        )
    ).json()
    assert p["parameters"]["schema_version"] == 3
    assert "fruit.renovation" not in p["quick_missing"]
    assert len(p["quick_required_keys"]) == len(p["quick_missing"])
    path = f"/api/profiles/{p['id']}"
    assert (await client.post(path + "/evaluations", json={"revision": 1})).status_code == 422
    bad = await client.patch(
        path + "/parameters",
        json={"revision": 1, "changes": {"fruit.cost_basis": "inclusive", "fruit.loss_rate": 0.1}},
    )
    assert bad.status_code == 422
    assert (
        await client.post(
            "/api/profiles", json={"name": "错", "city": "深圳", "parameters": fruit_data()}
        )
    ).status_code == 422


async def test_fruit_content_public_data_only(client, app, outbox, db):
    await register(client)
    await login(client)
    await verify(client, outbox)
    data = fruit_data()
    data["fruit"]["public_facts"] = {
        "base": {"products": "苹果、蜜柚", "retail_prices": "苹果8元/斤"}
    }
    p = (
        await client.post(
            "/api/profiles",
            json={
                "name": "街角水果",
                "city": "深圳",
                "industry": "fruit_retail",
                "parameters": data,
            },
        )
    ).json()
    path = f"/api/profiles/{p['id']}/content"
    topics = (await client.get(path + "/topics")).json()
    assert all(t["kind"] == "fruit_retail" for t in topics)
    app.state.ai_hub.start = lambda run_id, coro: coro.close()
    response = await client.post(
        path + "/drafts",
        json={"request_id": str(uuid4()), "platform": "xiaohongshu", "topic_id": "fruit:shopping"},
    )
    assert response.status_code == 200, response.text
    run = await db.scalar(select(AIRun).where(AIRun.kind == "content"))
    assert run.input["industry"] == "fruit_retail"
    assert run.input["store"]["public_facts"]["products"] == "苹果、蜜柚"
    source = next(
        s for s in response.json()["sources"] if s["title"] == "用户确认的水果零售公开资料"
    )
    assert "苹果8元/斤" in source["excerpt"]
    for internal in ("90000", "30000", "gross_margin", "loss_rate", "staff_cost", "parameters"):
        assert internal not in str(run.input)
        assert internal not in str(response.json()["sources"])


async def test_fruit_periodic_tool_does_arithmetic_and_preserves_revenue(client, app, outbox):
    import asyncio

    from .test_interview import FakeLLM, tool

    await register(client)
    await login(client)
    await verify(client, outbox)
    p = (
        await client.post(
            "/api/profiles", json={"name": "访谈水果", "city": "深圳", "industry": "fruit_retail"}
        )
    ).json()
    path = f"/api/profiles/{p['id']}"
    app.state.llm = FakeLLM(
        [
            tool(
                "record_periodic_value",
                {
                    "key": "fruit.sales_amount",
                    "amount": 3000,
                    "period": "day",
                    "reason": "用户明确日营业额",
                },
            ),
            tool(
                "record_periodic_value",
                {
                    "key": "fruit.staff_cost",
                    "amount": 300,
                    "period": "day",
                    "days_per_month": 26,
                    "staff_count": 2,
                    "reason": "两名付薪员工日薪",
                },
            ),
            {"role": "assistant", "content": "已记录日营业额与人工。"},
        ]
    )
    r = await client.post(
        path + "/interview/messages",
        json={
            "revision": 1,
            "request_id": str(uuid4()),
            "content": "日营业额3000，每名员工日薪300，每月26天，另请两名付薪员工",
        },
    )
    assert r.status_code == 200
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    result = (await client.get(path)).json()["parameters"]["fruit"]
    assert result["staff_cost"]["base"] == 15600
    assert result["sales_amount"]["base"] == 3000
    assert result["sales_period"]["base"] == "day"
    assert "fruit" in str(app.state.llm.calls)


def test_fruit_semantics_guards():
    for changes, text, previous in [
        ({"fruit.sales_amount": 300}, "两个人每天300", "每人月薪多少？"),
        ({"fruit.daily_transactions": 300}, "每天300", "工资多少？"),
        ({"fruit.avg_ticket": 8}, "苹果8元/斤", ""),
        ({"fruit.gross_margin": 0.3}, "加价三成", ""),
    ]:
        with pytest.raises(ValueError):
            guard_fruit(changes, text, previous)


async def test_fruit_report_numeric_verification_and_reuse(client, app, outbox):
    import asyncio

    from .test_interview import FakeLLM

    await register(client)
    await login(client)
    await verify(client, outbox)
    profile = (
        await client.post(
            "/api/profiles",
            json={
                "name": "报告水果",
                "city": "深圳",
                "industry": "fruit_retail",
                "stage": "preparing",
                "parameters": fruit_data(),
            },
        )
    ).json()
    path = f"/api/profiles/{profile['id']}"
    snapshot = (await client.post(path + "/evaluations", json={"revision": 1})).json()
    app.state.llm = FakeLLM(
        [
            {
                "role": "assistant",
                "content": "月营业额90000元，月采购成本70000元，扣老板报酬月结余300元，未扣5300元。参考备货资金7000元，缺口3000元。预测未来36个月；现金未知，请核实实际损耗与收入。",
            }
        ]
    )
    report_path = path + f"/evaluations/{snapshot['id']}/report"
    assert (await client.post(report_path, json={"request_id": str(uuid4())})).status_code == 200
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    result = (await client.get(report_path)).json()
    assert result["status"] == "succeeded", result
    assert "70000元" in result["content"]
    assert (await client.post(report_path, json={"request_id": str(uuid4())})).json()[
        "status"
    ] == "succeeded"
    assert len(app.state.llm.calls) == 1


async def test_fruit_copy_retries_platform_format_and_keeps_placeholders():
    from app.content.service import write_draft

    from .test_interview import FakeLLM

    good = "苹果和蜜柚，按自己的需要挑🍎\n\n苹果8元/斤。\n【待填：门店具体位置与自提时段】\n\n你更常买哪一种？\n#深圳水果 #苹果 #蜜柚 #水果选购"
    provider = FakeLLM(
        [
            {"role": "assistant", "content": "**小红书草稿**\n苹果卖得最多！"},
            {"role": "assistant", "content": good},
        ]
    )
    text, _ = await write_draft(
        provider,
        {
            "industry": "fruit_retail",
            "platform": "xiaohongshu",
            "store": {"public_facts": {"products": "苹果、蜜柚", "retail_prices": "苹果8元/斤"}},
        },
        "test",
    )
    assert text == good
    assert len(provider.calls) == 2
    assert "待填" in text
