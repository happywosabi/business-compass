from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.content.hot import collect, recommendations
from app.db.base import utcnow
from app.db.models import HotCollectionRun, HotTopic

from .test_interview import FakeLLM

pytestmark = pytest.mark.anyio


async def test_collection_filters_deduplicates_updates_rank_and_falls_back_without_vectors(
    app, db, monkeypatch
):
    real_client = httpx.AsyncClient
    feed = {
        "data": [
            {"title": "街角咖啡生活方式", "url": "https://example.com/coffee"},
            {"title": "街角咖啡，生活方式！", "url": "https://example.com/coffee"},
            {"title": "事故现场的奶茶店", "url": "https://example.com/bad"},
            {"title": "普通无关新闻", "url": "https://example.com/other"},
            {"title": "新款茶饮", "url": "javascript:alert(1)"},
        ]
    }

    def handler(request):
        if request.url.path == "/embeddings":
            return httpx.Response(503)
        return httpx.Response(200, json=feed)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler))
    )
    settings = app.state.settings.model_copy(
        update={"hotapi_base_url": "https://hot.example.com", "hotapi_channels": "weibo"}
    )
    assert (
        await collect(
            app.state.session_factory,
            settings,
            FakeLLM([{"role": "assistant", "content": '{"approved":[0]}'}]),
        )
        == 1
    )
    row = await db.scalar(select(HotTopic))
    assert row and row.embedding is None
    # 超过7天的相同标题仍复用已有记录，避免唯一索引冲突。
    row.fetched_at = utcnow() - timedelta(days=9)
    await db.execute(update(HotCollectionRun).values(created_at=utcnow() - timedelta(hours=3)))
    await db.commit()
    assert (
        await collect(
            app.state.session_factory,
            settings,
            FakeLLM([{"role": "assistant", "content": '{"approved":[0]}'}]),
        )
        == 0
    )
    candidates = await recommendations(db)
    assert len(candidates) == 1
    assert candidates[0]["sources"][0]["url"] == "https://example.com/coffee"
