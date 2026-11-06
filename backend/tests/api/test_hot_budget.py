import asyncio
from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from app.content import hot, search
from app.db.base import utcnow
from app.db.models import HotCollectionRun

from .test_content_hot import source
from .test_interview import FakeLLM

pytestmark = pytest.mark.anyio


async def test_public_budget_accounts_failure_and_rate_limits_retries(app, db, monkeypatch):
    async def news():
        return search.NewsBatch(
            [source()], [{"source": "chinanews_life", "status": "ok", "items": 1}]
        )

    monkeypatch.setattr(hot, "load_news", news)
    settings = app.state.settings.model_copy(update={"hot_daily_limit": 1, "hotapi_base_url": ""})
    provider = FakeLLM([{"role": "assistant", "content": "invalid-json"}])
    with pytest.raises(ValueError):
        await hot.collect(app.state.session_factory, settings, provider)
    run = await db.scalar(select(HotCollectionRun))
    assert run.status == "failed" and run.llm_calls == 1
    assert run.input_tokens > 0 and run.finished_at
    # 冷却已过，失败预约仍计入公共每日预算。
    await db.execute(update(HotCollectionRun).values(created_at=utcnow() - timedelta(hours=3)))
    await db.commit()
    assert await hot.collect(app.state.session_factory, settings, provider, force=True) == 0
    assert len(provider.calls) == 1


async def test_public_budget_concurrent_collection_timeout_is_recorded(app, db, monkeypatch):
    entered = asyncio.Event()

    async def news():
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(hot, "load_news", news)
    settings = app.state.settings.model_copy(update={"hot_run_seconds": 0.2, "hotapi_base_url": ""})
    provider = FakeLLM([])
    task = asyncio.create_task(hot.collect(app.state.session_factory, settings, provider))
    await asyncio.wait_for(entered.wait(), 5)
    assert await hot.collect(app.state.session_factory, settings, provider, force=True) == 0
    with pytest.raises(TimeoutError):
        await task
    run = await db.scalar(select(HotCollectionRun))
    assert run.status == "failed" and run.error == "TimeoutError"
    assert run.llm_calls == 0 and provider.calls == []


async def test_embedding_usage_is_recorded_with_public_run(app, db, monkeypatch):
    import httpx

    async def news():
        return search.NewsBatch(
            [source()], [{"source": "chinanews_life", "status": "ok", "items": 1}]
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(hot, "load_news", news)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "data": [{"index": 0, "embedding": [1, 0]}],
                        "usage": {"total_tokens": 12},
                    },
                )
            )
        ),
    )
    settings = app.state.settings.model_copy(
        update={
            "dashscope_api_key": SecretStr("fake"),
            "hotapi_base_url": "",
        }
    )
    provider = FakeLLM([{"role": "assistant", "content": '{"approved":[0]}'}])
    assert await hot.collect(app.state.session_factory, settings, provider) == 1
    run = await db.scalar(select(HotCollectionRun))
    assert (run.status, run.llm_calls, run.embedding_calls, run.embedding_tokens) == (
        "succeeded",
        1,
        1,
        12,
    )


async def test_sources_fail_without_model_calls_and_keep_safe_diagnostics(app, db, monkeypatch):
    async def news():
        return search.NewsBatch(
            [],
            [
                {
                    "source": "chinanews_life",
                    "status": "redirect",
                    "http_status": 302,
                    "body": "SECRET",
                }
            ],
        )

    monkeypatch.setattr(hot, "load_news", news)
    provider = FakeLLM([])
    settings = app.state.settings.model_copy(update={"hotapi_base_url": ""})
    with pytest.raises(ValueError, match="热点来源"):
        await hot.collect(app.state.session_factory, settings, provider)
    row = await db.scalar(select(HotCollectionRun))
    assert row.status == "failed" and row.llm_calls == row.embedding_calls == 0
    assert row.diagnostics["stage"] == "sources" and "SECRET" not in str(row.diagnostics)
    assert provider.calls == []


async def test_valid_empty_sources_succeed_without_model_and_reject_medical_topics(
    app, db, monkeypatch
):
    async def news():
        return search.NewsBatch(
            [source("水果与药物相冲"), source("奶茶糖尿病风险")],
            [{"source": "foodmate", "status": "ok", "items": 2}],
        )

    monkeypatch.setattr(hot, "load_news", news)
    provider = FakeLLM([])
    settings = app.state.settings.model_copy(update={"hotapi_base_url": ""})
    assert await hot.collect(app.state.session_factory, settings, provider) == 0
    row = await db.scalar(select(HotCollectionRun))
    assert row.status == "succeeded" and row.diagnostics["stage"] == "completed"
    assert row.diagnostics["candidates"] == 0 and provider.calls == []


@pytest.mark.parametrize(
    "raw",
    [
        '{"approved":[true]}',
        '{"approved":[-1]}',
        '{"approved":[3]}',
        '{"approved":[0],"url":"http://localhost"}',
    ],
)
async def test_invalid_model_selection_cannot_publish_or_fetch_urls(app, db, monkeypatch, raw):
    async def news():
        return search.NewsBatch([source()], [{"source": "foodmate", "status": "ok", "items": 1}])

    monkeypatch.setattr(hot, "load_news", news)
    settings = app.state.settings.model_copy(update={"hotapi_base_url": ""})
    with pytest.raises(ValueError):
        await hot.collect(
            app.state.session_factory, settings, FakeLLM([{"role": "assistant", "content": raw}])
        )
    from app.db.models import HotTopic

    assert await db.scalar(select(HotTopic)) is None
    row = await db.scalar(select(HotCollectionRun))
    assert row.status == "failed" and row.llm_calls == 1
    assert row.diagnostics["stage"] == "classification"
