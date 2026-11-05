import asyncio
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.content.service import topics
from app.db.base import utcnow
from app.db.models import User

from .helpers import login, register
from .test_interview import FakeLLM
from .test_profiles import create_profile

pytestmark = pytest.mark.anyio


async def test_content_two_step_sources_idempotency_and_ownership(client, other_client, app, db):
    await register(client)
    await login(client)
    profile = await create_profile(client)
    path = f"/api/profiles/{profile['id']}/content"
    choices = (await client.get(path + "/topics")).json()
    assert choices and all(c["sources"] for c in choices)
    assert (await client.get(path + "/drafts")).json() == []
    body = {
        "request_id": str(uuid4()),
        "topic_id": choices[-1]["id"],
        "platform": "moments",
        "confirmed_facts": "店里今天拍了煮茶视频",
    }
    assert (await client.post(path + "/drafts", json=body)).status_code == 403
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    app.state.llm = FakeLLM(
        [{"role": "assistant", "content": "今天，认真煮一壶茶。欢迎聊聊你喜欢的口味。"}]
    )
    draft = (await client.post(path + "/drafts", json=body)).json()
    assert draft["status"] == "running"
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    saved = (await client.get(path + "/drafts")).json()[0]
    assert saved["status"] == "succeeded"
    assert saved["sources"][:1] == choices[-1]["sources"]
    assert saved["sources"][-1]["excerpt"] == body["confirmed_facts"]
    repeat = (await client.post(path + "/drafts", json=body)).json()
    assert repeat["id"] == draft["id"]
    assert len(app.state.llm.calls) == 1
    await register(other_client, "other@example.com")
    await login(other_client, "other@example.com")
    for suffix in ["/topics", "/drafts"]:
        assert (await other_client.get(path + suffix)).status_code == 404


async def test_rejects_expired_or_invented_topic(client, db):
    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    p = await create_profile(client)
    assert (
        await client.post(
            f"/api/profiles/{p['id']}/content/drafts",
            json={"request_id": str(uuid4()), "topic_id": "invented", "platform": "moments"},
        )
    ).status_code == 422


def test_calendar_rollover_and_no_fake_holidays():
    class Profile:
        name = "饮品店"
        city = "杭州"

    result = topics(Profile(), date(2026, 12, 20))
    assert any(t["date"] == "2027-01-01" for t in result)
    assert all(t["date"] is None or t["date"] >= "2026-12-20" for t in result)


async def test_purge_deletes_only_expired_profile_with_dependents(client, db, milk_tea):
    from datetime import timedelta

    from app.db.models import Evaluation, Profile
    from app.worker import purge

    await register(client)
    await login(client)
    expired = await create_profile(client, parameters=milk_tea.model_dump(mode="json"))
    kept = await create_profile(client)
    saved = (
        await client.post(f"/api/profiles/{expired['id']}/evaluations", json={"revision": 1})
    ).json()
    from uuid import UUID

    await db.execute(
        update(Profile)
        .where(Profile.id == UUID(expired["id"]))
        .values(deleted_at=utcnow() - timedelta(days=31))
    )
    await db.execute(
        update(Profile)
        .where(Profile.id == UUID(kept["id"]))
        .values(deleted_at=utcnow() - timedelta(days=29))
    )
    await db.commit()
    assert await purge(db) == 1
    assert await db.get(Profile, UUID(expired["id"])) is None
    assert await db.get(Evaluation, UUID(saved["id"])) is None
    assert await db.get(Profile, UUID(kept["id"]))


def test_hot_candidate_filter_url_and_vector_similarity():
    from app.content.hot import BLOCK, RELEVANT, cosine, fingerprint, safe_url

    assert BLOCK.search("某地地震后饮品店捐赠")
    assert RELEVANT.search("咖啡与城市漫步")
    assert not safe_url("javascript:alert(1)")
    assert not safe_url("https://user:password@example.com/")
    assert safe_url("https://example.com/article")
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0
    assert cosine([1], [1, 2]) == 0
    assert fingerprint("咖啡，散步！") == fingerprint("咖啡散步")
