"""档案完整生命周期、越权与事务并发回归。"""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.db.base import utcnow
from app.db.models import ParameterChange, Profile

from .helpers import PASSWORD, login, register

pytestmark = pytest.mark.anyio


async def create_profile(client, **overrides):
    body = {"name": "大学城奶茶店", "city": "杭州", **overrides}
    response = await client.post("/api/profiles", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def owner(client):
    await register(client)
    await login(client)
    return client


async def test_template_metadata_comes_from_engine(owner):
    response = await owner.get("/api/templates")
    assert response.status_code == 200
    template = response.json()[0]
    assert template["version"] == 1
    assert template["industries"] == [
        {"code": "drinks", "label": "饮品"},
        {"code": "fruit_retail", "label": "水果店（零售）"},
    ]
    assert len([f for f in template["fields"] if f["quick_required"]]) == 7
    channel = next(f for f in template["fields"] if f["key"] == "revenue.channels")
    assert channel["value_schema"]["type"] == "array"
    assert "Channel" in template["definitions"]


async def test_create_edit_and_history(owner):
    profile = await create_profile(owner, name="  奶茶店  ")
    path = f"/api/profiles/{profile['id']}"
    assert profile["name"] == "奶茶店"
    assert len(profile["quick_missing"]) == 7
    assert profile["revision"] == 1
    response = await owner.patch(
        path + "/parameters",
        json={
            "revision": 1,
            "changes": {"fixed_cost.rent": {"base": 12000, "source": "actual"}},
            "reason": "房东报价",
        },
    )
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["revision"] == 2
    assert profile["parameters"]["fixed_cost"]["rent"]["source"] == "user"
    assert "fixed_cost.rent" not in profile["quick_missing"]
    history = (await owner.get(path + "/changes")).json()
    assert len(history) == 1
    assert history[0]["reason"] == "房东报价"
    assert history[0]["new_value"]["base"] == 12000
    assert history[0]["profile_revision"] == 2
    persisted = (await owner.get(path)).json()
    assert persisted == profile
    edited = await owner.patch(path, json={"revision": 2, "stage": "preparing", "city": "上海"})
    assert edited.status_code == 200
    assert edited.json()["city"] == "上海"


async def test_delete_restore_archive_and_copy(owner):
    original = await create_profile(owner, parameters={"revenue": {"avg_ticket": {"base": 15}}})
    path = f"/api/profiles/{original['id']}"
    duplicate = (await owner.post(path + "/copy", json={"revision": 1})).json()
    assert duplicate["id"] != original["id"]
    assert duplicate["revision"] == 1
    assert duplicate["parameters"] == original["parameters"]
    await owner.patch(
        path + "/parameters", json={"revision": 1, "changes": {"revenue.avg_ticket": 18}}
    )
    assert (await owner.get(f"/api/profiles/{duplicate['id']}")).json()["parameters"]["revenue"][
        "avg_ticket"
    ]["base"] == 15
    assert (await owner.delete(path, params={"revision": 2})).status_code == 204
    assert (await owner.get(path)).status_code == 404
    deleted = (await owner.get("/api/profiles?view=deleted")).json()["items"]
    assert [p["id"] for p in deleted] == [original["id"]]
    restored = await owner.post(path + "/restore", json={"revision": 3})
    assert restored.status_code == 200
    assert restored.json()["revision"] == 4
    archived = await owner.patch(path, json={"revision": 4, "status": "archived"})
    assert archived.status_code == 200
    assert original["id"] not in [
        p["id"] for p in (await owner.get("/api/profiles")).json()["items"]
    ]
    assert (await owner.get("/api/profiles?view=archived")).json()["items"][0]["id"] == original[
        "id"
    ]


async def test_restore_expiry(owner, db):
    profile = await create_profile(owner)
    await db.execute(
        update(Profile)
        .where(Profile.id == profile["id"])
        .values(deleted_at=utcnow() - timedelta(days=31))
    )
    await db.commit()
    assert (
        await owner.post(f"/api/profiles/{profile['id']}/restore", json={"revision": 1})
    ).status_code == 404
    assert (await owner.get("/api/profiles?view=deleted")).json()["items"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"fixed_cost.rent": -1},
        {"unknown.key": 2},
        {"revenue.opening_month": 13},
        {"revenue.channels": [{"name": "堂食", "share": 0.5, "fee_rate": 0}]},
        {"fixed_cost.rent": "Infinity"},
    ],
)
async def test_invalid_changes_are_atomic(owner, changes):
    profile = await create_profile(owner)
    path = f"/api/profiles/{profile['id']}"
    response = await owner.patch(path + "/parameters", json={"revision": 1, "changes": changes})
    assert response.status_code == 422
    assert (await owner.get(path)).json()["revision"] == 1
    assert (await owner.get(path + "/changes")).json() == []


async def test_stale_revision_never_overwrites_or_adds_history(owner):
    profile = await create_profile(owner)
    path = f"/api/profiles/{profile['id']}"
    await owner.patch(
        path + "/parameters", json={"revision": 1, "changes": {"fixed_cost.rent": 10000}}
    )
    stale = await owner.patch(
        path + "/parameters", json={"revision": 1, "changes": {"fixed_cost.rent": 999}}
    )
    assert stale.status_code == 409
    assert (await owner.post(path + "/copy", json={"revision": 1})).status_code == 409
    assert (await owner.delete(path, params={"revision": 1})).status_code == 409
    assert (await owner.get(path)).json()["parameters"]["fixed_cost"]["rent"]["base"] == 10000
    assert len((await owner.get(path + "/changes")).json()) == 1


async def test_two_real_concurrent_edits_have_one_winner(owner, app):
    profile = await create_profile(owner)
    path = f"/api/profiles/{profile['id']}/parameters"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", cookies=owner.cookies
    ) as second:
        responses = await asyncio.gather(
            owner.patch(path, json={"revision": 1, "changes": {"fixed_cost.rent": 10000}}),
            second.patch(path, json={"revision": 1, "changes": {"revenue.avg_ticket": 15}}),
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len((await owner.get(path.replace("parameters", "changes"))).json()) == 1


async def test_defaults_and_derived_staleness(owner):
    profile = await create_profile(owner, parameters={"revenue": {"avg_ticket": {"base": 15}}})
    path = f"/api/profiles/{profile['id']}"
    default = await owner.post(
        path + "/defaults", json={"revision": 1, "keys": ["variable_cost.unit_cost"]}
    )
    assert default.status_code == 200
    assert default.json()["parameters"]["variable_cost"]["unit_cost"]["base"] == 5.4
    changed = await owner.patch(
        path + "/parameters", json={"revision": 2, "changes": {"revenue.avg_ticket": 20}}
    )
    assert changed.json()["derived_stale_keys"] == ["variable_cost.unit_cost"]
    recomputed = await owner.post(
        path + "/defaults", json={"revision": 3, "keys": ["variable_cost.unit_cost"]}
    )
    assert recomputed.json()["parameters"]["variable_cost"]["unit_cost"]["base"] == 7.2
    assert recomputed.json()["derived_stale_keys"] == []
    assert (
        await owner.post(path + "/defaults", json={"revision": 4, "keys": ["fixed_cost.rent"]})
    ).status_code == 422


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("GET", "", None),
        ("PATCH", "", {"revision": 1, "name": "窃取"}),
        ("PATCH", "/parameters", {"revision": 1, "changes": {"fixed_cost.rent": 0}}),
        ("POST", "/copy", {"revision": 1}),
        ("DELETE", "?revision=1", None),
        ("GET", "/changes", None),
        ("POST", "/defaults", {"revision": 1, "keys": ["revenue.open_days"]}),
        ("POST", "/restore", {"revision": 1}),
    ],
)
async def test_every_profile_operation_rejects_other_owner(
    owner, other_client, method, suffix, payload
):
    profile = await create_profile(owner)
    await register(other_client, "other@example.com", PASSWORD)
    await login(other_client, "other@example.com", PASSWORD)
    response = await other_client.request(
        method, f"/api/profiles/{profile['id']}{suffix}", json=payload
    )
    assert response.status_code == 404, response.text
    assert (await other_client.get("/api/profiles")).json()["items"] == []


async def test_login_required_and_unknown_ids(client):
    assert (await client.get("/api/profiles")).status_code == 401
    await register(client)
    await login(client)
    assert (await client.get(f"/api/profiles/{uuid4()}")).status_code == 404
    assert (
        await client.post("/api/profiles", json={"name": " ", "city": "杭州"})
    ).status_code == 422
    assert (
        await client.post(
            "/api/profiles", json={"name": "饭店", "city": "杭州", "industry": "restaurant"}
        )
    ).status_code == 422


async def test_invalid_update_leaves_database_untouched(owner, db):
    profile = await create_profile(owner)
    response = await owner.patch(
        f"/api/profiles/{profile['id']}", json={"revision": 1, "name": None}
    )
    assert response.status_code == 422
    assert await db.scalar(select(func.count()).select_from(ParameterChange)) == 0


async def test_rejects_reversed_cost_tiers_without_writing(client):
    await register(client)
    await login(client)
    profile = await create_profile(client)
    path = f"/api/profiles/{profile['id']}"
    invalid = await client.patch(
        path + "/parameters",
        json={
            "revision": 1,
            "changes": {
                "startup.renovation": {"base": 75000, "pessimistic": 70000, "optimistic": 80000}
            },
        },
    )
    assert invalid.status_code == 422
    assert "三档方向" in invalid.json()["detail"]
    assert (await client.get(path)).json()["revision"] == 1


async def test_longer_rent_increase_interval_is_favorable_and_opening_month_unordered(client):
    await register(client)
    await login(client)
    profile = await create_profile(client)
    response = await client.patch(
        f"/api/profiles/{profile['id']}/parameters",
        json={
            "revision": 1,
            "changes": {
                "fixed_cost.rent_increase_every_years": {
                    "base": 2,
                    "pessimistic": 1,
                    "optimistic": 3,
                },
                "revenue.opening_month": {"base": 6, "pessimistic": 12, "optimistic": 1},
            },
        },
    )
    assert response.status_code == 200, response.text
