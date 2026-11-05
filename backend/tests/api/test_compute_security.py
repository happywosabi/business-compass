import asyncio
import time
from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.db.models import CalculationRun
from app.engine.orchard import OrchardParams
from app.evaluations.compute import _isolated
from tests.engine.test_orchard import orchard_data

from .helpers import login, register

pytestmark = pytest.mark.anyio


def stall(connection, *args):
    while True:
        time.sleep(1)


async def test_compute_timeout_kills_child_and_leaves_event_loop_responsive():
    import multiprocessing

    before = {p.pid for p in multiprocessing.active_children()}
    ticks = 0

    async def pulse():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks += 1

    with pytest.raises(HTTPException) as error:
        await asyncio.gather(_isolated(None, None, None, 0.3, target=stall), pulse())
    assert error.value.status_code == 503
    assert ticks >= 15
    assert {p.pid for p in multiprocessing.active_children()} == before


async def test_budget_is_shared_by_create_preview_and_failed_work(client, app, db):
    await register(client)
    await login(client)
    app.state.settings.calculation_per_minute = 1
    profile = (
        await client.post(
            "/api/profiles",
            json={
                "name": "果园",
                "city": "梅州",
                "template_key": "orchard",
                "parameters": orchard_data(),
            },
        )
    ).json()
    path = f"/api/profiles/{profile['id']}"
    # 未验证邮箱仍能手工测算，但会占用相同计算预算。
    response = await client.post(
        path + "/what-if", json={"revision": 1, "changes": {"orchard.unpaid_labor": 1000}}
    )
    assert response.status_code == 200, response.text
    assert (await client.post(path + "/evaluations", json={"revision": 1})).status_code == 429
    assert await db.scalar(select(func.count()).select_from(CalculationRun)) == 1


async def test_complex_orchard_api_does_not_block_health(client, app):
    await register(client)
    await login(client)
    data = orchard_data()
    original = data["orchard"]["varieties"]["base"][0]
    varieties = []
    for i in range(10):
        v = deepcopy(original)
        v["id"] = f"v{i}"
        v["harvest_kg"].update(pessimistic=8000, optimistic=12000)
        v["grades"] = []
        for j in range(5):
            grade = deepcopy(original["grades"][0])
            grade.update(id=f"g{j}", share=0.2)
            v["grades"].append(grade)
        varieties.append(v)
    data["orchard"]["varieties"]["base"] = varieties
    params = OrchardParams.model_validate(data)
    assert not params.missing_keys()
    profile = (
        await client.post(
            "/api/profiles",
            json={
                "name": "复杂果园",
                "city": "梅州",
                "template_key": "orchard",
                "parameters": data,
            },
        )
    ).json()
    request = asyncio.create_task(
        client.post(
            f"/api/profiles/{profile['id']}/what-if",
            json={"revision": 1, "changes": {"orchard.unpaid_labor": 1000}},
        )
    )
    try:
        for _ in range(5):
            await asyncio.sleep(0.01)
            started = time.monotonic()
            assert (await client.get("/api/health")).status_code == 200
            assert time.monotonic() - started < 0.3
        assert (await request).status_code == 200
    finally:
        await asyncio.gather(request, return_exceptions=True)


async def test_user_concurrency_timeout_and_daily_budget_release_slots(
    client, app, db, monkeypatch
):
    from datetime import timedelta

    from sqlalchemy import update

    from app.db.base import utcnow
    from app.evaluations import compute as module

    await register(client)
    await login(client)
    profile = (
        await client.post(
            "/api/profiles",
            json={
                "name": "果园",
                "city": "梅州",
                "template_key": "orchard",
                "parameters": orchard_data(),
            },
        )
    ).json()
    path = f"/api/profiles/{profile['id']}/what-if"
    body = {"revision": 1, "changes": {"orchard.unpaid_labor": 1000}}
    entered, release = asyncio.Event(), asyncio.Event()
    real = module._isolated

    async def wait_then_fail(*args):
        entered.set()
        await release.wait()
        raise HTTPException(503, "test timeout")

    monkeypatch.setattr(module, "_isolated", wait_then_fail)
    pending = asyncio.create_task(client.post(path, json=body))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        assert (await client.post(path, json=body)).status_code == 429
    finally:
        release.set()
    assert (await pending).status_code == 503
    assert await db.scalar(select(func.count()).select_from(CalculationRun)) == 1
    # 超时后计算槽已释放；失败预算仍保留到日上限。
    monkeypatch.setattr(module, "_isolated", real)
    app.state.settings.calculation_per_day = 1
    await db.execute(update(CalculationRun).values(created_at=utcnow() - timedelta(minutes=2)))
    await db.commit()
    assert (await client.post(path, json=body)).status_code == 429
    app.state.settings.calculation_per_day = 2
    assert (await client.post(path, json=body)).status_code == 200


async def test_two_global_slots_are_shared_across_users(client, other_client, app, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.evaluations import compute as module

    third = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    clients = [client, other_client, third]
    paths = []
    for i, device in enumerate(clients):
        email = f"compute-{i}@example.com"
        await register(device, email)
        await login(device, email)
        profile = (
            await device.post(
                "/api/profiles",
                json={
                    "name": "果园",
                    "city": "梅州",
                    "template_key": "orchard",
                    "parameters": orchard_data(),
                },
            )
        ).json()
        paths.append(f"/api/profiles/{profile['id']}/what-if")
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def slow(*args):
        nonlocal count
        count += 1
        if count == 2:
            entered.set()
        await release.wait()
        raise HTTPException(503, "test stopped")

    monkeypatch.setattr(module, "_isolated", slow)
    body = {"revision": 1, "changes": {"orchard.unpaid_labor": 1000}}
    tasks = [
        asyncio.create_task(c.post(p, json=body))
        for c, p in zip(clients[:2], paths[:2], strict=True)
    ]
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert (await third.post(paths[2], json=body)).status_code == 503
        assert count == 2
    finally:
        release.set()
        await asyncio.gather(*tasks)
        await third.aclose()
