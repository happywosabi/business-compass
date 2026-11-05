import asyncio
import json
from datetime import timedelta
from email.utils import format_datetime
from uuid import UUID, uuid4
from xml.sax.saxutils import escape

import httpx
import pytest
from sqlalchemy import select, update

from app.content import hot, search
from app.db.base import utcnow
from app.db.models import AIRun, HotTopic, User

from .helpers import login, register
from .test_interview import FakeLLM
from .test_profiles import create_profile

pytestmark = pytest.mark.anyio


def source(title="咖啡城市漫步新话题", **extra):
    return {
        "title": title,
        "url": "https://example.com/article",
        "excerpt": "报道介绍了沿街咖啡与城市漫步的日常场景。",
        "published_at": (utcnow() - timedelta(hours=1)).isoformat(),
        "retrieved_at": utcnow().isoformat(),
        "publisher": "示例媒体",
        "kind": "news_summary",
        **extra,
    }


async def test_online_search_reads_real_response_filters_dates_and_never_follows_article(
    monkeypatch,
):
    now = utcnow()
    rows = []
    for title, days, link in [
        (
            "咖啡与城市漫步",
            0,
            "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fexample.com%2Farticle",
        ),
        ("旧报道", 9, "https://example.com/old"),
        ("未来报道", -2, "https://example.com/future"),
        ("坏链接", 0, "javascript:alert(1)"),
    ]:
        rows.append(
            f"<item><title>{title}</title><link>{escape(link)}</link><description>&lt;b&gt;真实摘要&lt;/b&gt;</description><pubDate>{format_datetime(now - timedelta(days=days))}</pubDate></item>"
        )
    xml = "<rss><channel>" + "".join(rows) + "</channel></rss>"
    real_client, requests = httpx.AsyncClient, []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=xml)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler))
    )
    result = await search.search_news("咖啡")
    assert len(result) == 1
    assert result[0]["excerpt"] == "真实摘要"
    assert result[0]["url"] == "https://example.com/article"
    assert len(requests) == 1 and requests[0].url.host == "www.bing.com"
    assert requests[0].url.params["q"] == "咖啡"


async def test_online_search_rejects_entities_and_oversized_response(monkeypatch):
    real_client = httpx.AsyncClient
    for body in ['<!DOCTYPE rss [<!ENTITY a "x">]><rss/>', "a" * (search.MAX_BYTES + 1)]:
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda body=body, **kw: real_client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
            ),
        )
        with pytest.raises(ValueError):
            await search.search_news("咖啡")


async def test_research_matches_topic_and_reports_live_cached_or_title_only(monkeypatch):
    topic = {"title": "咖啡城市漫步新话题", "sources": [source()]}

    async def results(query):
        return [source("无关的水果促销"), source()]

    monkeypatch.setattr(search, "search_news", results)
    result = await search.research(topic)
    assert result["status"] == "live" and len(result["sources"]) == 1

    async def failed(query):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(search, "search_news", failed)
    assert (await search.research(topic))["status"] == "cached"
    topic["sources"] = [source(kind="hot_title", excerpt=topic["title"])]
    result = await search.research(topic)
    assert result["status"] == "title_only" and "仅提供标题" in result["note"]


@pytest.mark.parametrize(
    "template_key,title",
    [("physical_store", "咖啡城市漫步新话题"), ("orchard", "果园水果采摘新话题")],
)
async def test_selected_hot_researched_persisted_and_idempotent(
    client, app, db, monkeypatch, template_key, title
):
    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    if template_key == "orchard":
        profile = (
            await client.post(
                "/api/profiles",
                json={"name": "测试果园", "city": "梅州", "template_key": "orchard"},
            )
        ).json()
    else:
        profile = await create_profile(client)
    row = HotTopic(
        fingerprint=hot.fingerprint(title),
        title=title,
        url="https://example.com/article",
        channel="news",
        rank=1,
        safe=True,
        sources=[source(title)],
    )
    db.add(row)
    await db.commit()
    path = f"/api/profiles/{profile['id']}/content"
    choices = (await client.get(path + "/topics")).json()
    assert all(t["kind"] != "hot" for t in choices)
    hot_choices = (await client.get(path + "/hot-topics")).json()
    assert len(hot_choices) == 1

    async def results(query):
        assert query == title
        return [source(title, excerpt="本次重新检索到的真实摘要，不能用作本店承诺。")]

    monkeypatch.setattr(search, "search_news", results)
    app.state.llm = FakeLLM([{"role": "assistant", "content": title + "，一起聊聊自己的日常。"}])
    body = {
        "request_id": str(uuid4()),
        "topic_id": choices[-1]["id"],
        "hot_topic_id": hot_choices[0]["id"],
        "platform": "moments",
    }
    response = await client.post(path + "/drafts", json=body)
    assert response.status_code == 200, response.text
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    saved = (await client.get(path + "/drafts")).json()[0]
    assert saved["status"] == "succeeded"
    assert any(s.get("status") == "live" for s in saved["sources"])
    assert any("本次重新检索" in s["excerpt"] for s in saved["sources"])
    payload = json.loads(app.state.llm.calls[0][-1]["content"].split("\n", 1)[1])
    assert payload["hot_research"]["status"] == "live"
    assert payload["topic"]["id"] == choices[-1]["id"]
    assert "parameters" not in payload
    run = await db.scalar(select(AIRun).where(AIRun.request_id == UUID(body["request_id"])))
    assert run.output["hot_research"]["status"] == "live"
    row.fetched_at = utcnow() - timedelta(days=2)
    await db.commit()
    assert (await client.post(path + "/drafts", json=body)).json()["id"] == saved["id"]
    assert len(app.state.llm.calls) == 1
    assert (
        await client.post(path + "/drafts", json={**body, "hot_topic_id": None})
    ).status_code == 409
    assert (
        await client.post(path + "/drafts", json={**body, "request_id": str(uuid4())})
    ).status_code == 422


async def test_hot_endpoint_ownership_verification_and_no_paid_collection(
    client, other_client, app, db, monkeypatch
):
    await register(client)
    await login(client)
    p = await create_profile(client)
    path = f"/api/profiles/{p['id']}/content"
    assert (await client.post(path + "/hot-topics/refresh")).status_code == 403
    await register(other_client, "other@example.com")
    await login(other_client, "other@example.com")
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    assert (await other_client.get(path + "/hot-topics")).status_code == 404
    assert (await other_client.post(path + "/hot-topics/refresh")).status_code == 404
    calls = []

    async def fail(*args, **kw):
        calls.append(1)
        raise ValueError("offline")

    monkeypatch.setattr(hot, "collect", fail)
    await db.execute(update(User).values(daily_ai_quota=0))
    await db.commit()
    for _ in range(2):
        result = (await client.post(path + "/hot-topics/refresh")).json()
        assert result["error"] is None and result["topics"] == []
        assert "不调用 AI" in result["message"]
    assert calls == []
    assert await db.scalar(select(AIRun)) is None


async def test_collection_partial_failure_summary_provenance_and_template_matching(
    app, db, monkeypatch
):
    async def results(query):
        if "咖啡" in query:
            raise httpx.ConnectError("offline")
        return [source("果园水果采摘新话题")]

    async def no_vectors(*args):
        return [None]

    monkeypatch.setattr(hot, "search_news", results)
    monkeypatch.setattr(hot, "embed", no_vectors)
    provider = FakeLLM([{"role": "assistant", "content": '{"approved":[0]}'}])
    settings = app.state.settings.model_copy(update={"hotapi_base_url": ""})
    assert await hot.collect(app.state.session_factory, settings, provider) == 1
    assert await hot.recommendations(db) == []
    choices = await hot.recommendations(db, "orchard")
    assert choices[0]["sources"][0]["publisher"] == "示例媒体"
    assert await hot.collect(app.state.session_factory, settings, provider, force=True) == 0
    assert len(provider.calls) == 1


async def test_news_background_cannot_authorize_invented_business_scene():
    from app.content.service import write_draft

    data = {
        "template_key": "orchard",
        "hot_topic": {"title": "果园采摘", "sources": []},
        "hot_research": {"status": "live", "sources": [source(excerpt="报道中的果农正在分拣装车")]},
        "store": {"supply": {"supply_dates": "11月1日至20日"}},
    }
    provider = FakeLLM(
        [
            {"role": "assistant", "content": "我们正忙着分拣、装车。"},
            {
                "role": "assistant",
                "content": "从果园话题聊聊这季供货。\n供货期为11月1日至20日。\n【待填：果园真实现场故事】",
            },
        ]
    )
    content, _ = await write_draft(provider, data, "fake")
    assert "忙着分拣" not in content and len(provider.calls) == 2


async def test_cancel_during_hot_research_never_calls_writing_model(client, app, db, monkeypatch):
    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    profile = await create_profile(client)
    row = HotTopic(
        fingerprint=hot.fingerprint("咖啡取消验收"),
        title="咖啡取消验收",
        url="https://example.com/article",
        channel="news",
        rank=1,
        safe=True,
        sources=[source("咖啡取消验收")],
    )
    db.add(row)
    await db.commit()
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(topic):
        entered.set()
        await release.wait()
        return {"status": "live", "sources": [source()], "note": "已检索"}

    monkeypatch.setattr("app.content.service.research", delayed)
    app.state.llm = FakeLLM([])
    body = {
        "request_id": str(uuid4()),
        "topic_id": "evergreen:process",
        "hot_topic_id": f"hot:{row.id}",
        "platform": "moments",
    }
    path = f"/api/profiles/{profile['id']}/content/drafts"
    await client.post(path, json=body)
    await entered.wait()
    run = await db.scalar(select(AIRun).where(AIRun.request_id == UUID(body["request_id"])))
    run.cancel_requested = True
    await db.commit()
    release.set()
    await asyncio.gather(*list(app.state.ai_hub.tasks.values()))
    assert app.state.llm.calls == []
    assert (await client.get(path)).json()[0]["status"] == "failed"
