"""快照不可变、试算基准、并发和越权。"""

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import PASSWORD, login, register
from .test_profiles import create_profile

pytestmark = pytest.mark.anyio


@pytest.fixture
async def prepared(client, milk_tea):
    await register(client)
    await login(client)
    profile = await create_profile(client, parameters=milk_tea.model_dump(mode="json"))
    return client, profile


async def test_full_example_and_snapshot_immutability(prepared):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}"
    response = await client.post(path + "/evaluations", json={"revision": 1})
    assert response.status_code == 201, response.text
    snapshot = response.json()
    base = snapshot["results"]["scenarios"]["base"]
    assert base["payback_month"] == 21
    assert base["suggested_funding"] == [341040, 378040]
    assert snapshot["engine_version"] == "1.0.1"
    assert snapshot["template_version"] == 1
    assert snapshot["profile_revision"] == 2
    snapshot_path = path + f"/evaluations/{snapshot['id']}"
    await client.patch(
        path + "/parameters", json={"revision": 2, "changes": {"revenue.avg_ticket": 30}}
    )
    assert (await client.get(snapshot_path)).json() == snapshot
    history = (await client.get(path + "/evaluations")).json()
    assert history == [snapshot]
    label = await client.patch(snapshot_path, json={"label": "签约前"})
    assert label.status_code == 200
    assert label.json()["label"] == "签约前"
    assert label.json()["parameters"] == snapshot["parameters"]
    assert (
        await client.patch(snapshot_path, json={"label": "x", "results": {}})
    ).status_code == 422


async def test_required_employees_not_silently_defaulted(prepared):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}"
    await client.patch(
        path + "/parameters", json={"revision": 1, "changes": {"fixed_cost.staff": None}}
    )
    result = await client.post(path + "/evaluations", json={"revision": 2})
    assert result.status_code == 422
    assert "员工" in result.json()["detail"]
    assert (await client.get(path)).json()["revision"] == 2
    assert (await client.get(path + "/evaluations")).json() == []


async def test_default_fill_and_audit_are_one_transaction(prepared):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}"
    await client.patch(
        path + "/parameters", json={"revision": 1, "changes": {"revenue.open_days": None}}
    )
    response = await client.post(path + "/evaluations", json={"revision": 2})
    assert response.status_code == 201
    item = response.json()
    assert item["parameters"]["revenue"]["open_days"]["source"] == "default"
    assert item["profile_revision"] == 3
    changes = (await client.get(path + "/changes")).json()
    assert any(
        c["parameter_key"] == "revenue.open_days"
        and c["source"] == "default"
        and c["profile_revision"] == 3
        for c in changes
    )


async def test_what_if_uses_snapshot_and_does_not_write(prepared):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}"
    snapshot = (await client.post(path + "/evaluations", json={"revision": 1})).json()
    await client.patch(
        path + "/parameters", json={"revision": 2, "changes": {"revenue.avg_ticket": 30}}
    )
    before = (await client.get(path)).json()
    response = await client.post(
        path + "/what-if",
        json={
            "revision": 3,
            "evaluation_id": snapshot["id"],
            "changes": {"fixed_cost.rent": 10000},
        },
    )
    assert response.status_code == 200
    assert response.json()["before"]["steady_monthly_cash"] == 13400
    assert response.json()["after"]["steady_monthly_cash"] == 15400
    assert (await client.get(path)).json() == before
    applied = await client.post(
        path + "/what-if/apply",
        json={
            "revision": 3,
            "evaluation_id": snapshot["id"],
            "changes": {"fixed_cost.rent": 10000},
        },
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["results"]["scenarios"]["base"]["steady_monthly_cash"] == 15400
    assert applied.json()["parameters"]["revenue"]["avg_ticket"]["base"] == 15
    assert applied.json()["parameters"]["fixed_cost"]["rent"]["source"] == "user"
    assert (
        await client.post(
            path + "/what-if/apply",
            json={
                "revision": 3,
                "evaluation_id": snapshot["id"],
                "changes": {"fixed_cost.rent": 10000},
            },
        )
    ).status_code == 409


async def test_concurrent_evaluations_only_one_commits(prepared, app):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}/evaluations"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", cookies=client.cookies
    ) as second:
        responses = await asyncio.gather(
            client.post(path, json={"revision": 1}), second.post(path, json={"revision": 1})
        )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len((await client.get(path)).json()) == 1


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "/evaluations", None),
        ("POST", "/evaluations", {"revision": 1}),
        ("GET", "/evaluations/{eid}", None),
        ("PATCH", "/evaluations/{eid}", {"label": "偷改"}),
        ("POST", "/what-if", {"revision": 1, "changes": {"fixed_cost.rent": 1}}),
        (
            "POST",
            "/what-if/apply",
            {"revision": 1, "evaluation_id": str(uuid4()), "changes": {"fixed_cost.rent": 1}},
        ),
    ],
)
async def test_every_snapshot_endpoint_is_owned(prepared, other_client, method, suffix, body):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}"
    item = (await client.post(path + "/evaluations", json={"revision": 1})).json()
    await register(other_client, "other@example.com", PASSWORD)
    await login(other_client, "other@example.com", PASSWORD)
    response = await other_client.request(
        method, path + suffix.replace("{eid}", item["id"]), json=body
    )
    assert response.status_code == 404


async def test_snapshot_must_belong_to_url_profile(prepared):
    client, profile = prepared
    path = f"/api/profiles/{profile['id']}"
    item = (await client.post(path + "/evaluations", json={"revision": 1})).json()
    other = await create_profile(client)
    assert (
        await client.get(f"/api/profiles/{other['id']}/evaluations/{item['id']}")
    ).status_code == 404
