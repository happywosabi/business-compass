import asyncio
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.content.service import topics, unsupported_details, write_draft
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


async def test_platform_draft_retries_invented_rules_and_preserves_confirmed_facts():
    provider = FakeLLM(
        [
            {"role": "assistant", "content": "买奶茶送周边，款式随机，先到先选！"},
            {
                "role": "assistant",
                "content": "深圳奶茶搭子🥤今天来领哪吒周边\n\n买奶茶就送哪吒周边🎁\n\n🎁【待填：赠品款式及领取规则，是否随机请确认】\n\n今天最想喝哪杯？\n\n#深圳奶茶 #哪吒仙饮 #哪吒周边 #奶茶搭子",
            },
        ]
    )
    facts = {
        "confirmed_facts": "今天买奶茶送哪吒周边",
        "platform": "xiaohongshu",
        "voice": "playful",
    }
    content, usage = await write_draft(provider, facts, "fake")
    assert "【待填：赠品款式及领取规则，是否随机请确认】" in content
    assert "先到先选" not in content and "买奶茶就送哪吒周边" in content
    assert len(provider.calls) == 2 and usage["prompt_tokens"] == 20
    assert not unsupported_details("周边款式随机", {"confirmed_facts": "周边随机赠送"})
    provider = FakeLLM([{"role": "assistant", "content": "热量200大卡，无负担"}] * 2)
    with pytest.raises(ValueError, match="未确认"):
        await write_draft(provider, facts, "fake")


def test_unknown_claims_must_be_wholly_inside_fillable_fields():
    facts = {"confirmed_facts": "今天送周边。未确定款式是否随机。没有销量数据。"}
    draft = "买奶茶送周边🎁\n【待填：当天真实天气】\n【待填：卖得最多的真实饮品及统计依据】"
    assert not unsupported_details(draft, facts)
    assert unsupported_details("天气热，来一杯【待填：饮品名】", facts)
    assert unsupported_details("卖得最多的是【待填：饮品名】", facts)
    assert unsupported_details("款式随机", facts)
    assert unsupported_details("热销榜", {"confirmed_facts": "想写热销推荐，未提供销量数据"})
    assert not unsupported_details("热销榜", {"confirmed_facts": "上周热销第一是奶绿"})


async def test_draft_does_not_accept_a_questionnaire_of_placeholders():
    many = "\n".join(f"【待填：第{i}项信息】" for i in range(4))
    provider = FakeLLM([{"role": "assistant", "content": many}] * 2)
    with pytest.raises(ValueError, match="过多待填项"):
        await write_draft(provider, {}, "fake")


def test_orchard_unknown_claims_can_be_specific_placeholders():
    from app.content.service import unsupported_details

    data = {
        "template_key": "orchard",
        "confirmed_facts": "",
        "store": {"supply": {"supply_dates": "11月1日至20日"}},
    }
    assert unsupported_details("进入采收期，统货大小不一，包邮次日达，有机蜜柚", data)
    assert unsupported_details("【待填：采收日期、包装规格与发货规则】", data) == []
