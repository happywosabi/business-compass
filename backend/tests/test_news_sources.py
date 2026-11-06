"""资讯抓取的网络边界、格式边界和来源降级；不访问真实网络。"""

import gzip
from datetime import timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.content import fetch, search
from app.content.diagnostics import public_diagnostics
from app.db.base import utcnow

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def rss(title="水果采摘新话题", date=None, link="https://example.com/article"):
    date = date or format_datetime(utcnow() - timedelta(hours=1))
    return f"<rss><channel><item><title>{title}</title><link>{link}</link><description>真实摘要</description><pubDate>{date}</pubDate></item></channel></rss>".encode()


async def test_fixed_feeds_partial_failure_does_not_follow_redirect_or_article(monkeypatch):
    real_client, requests = httpx.AsyncClient, []

    def handler(request):
        requests.append(request)
        if request.url.path == "/rss/life.xml":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest"})
        if request.url.path == "/rss/finance.xml":
            return httpx.Response(503, text="PRIVATE_UPSTREAM_BODY")
        return httpx.Response(200, content=rss())

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler))
    )
    batch = await search.load_news()
    assert len(batch.rows) == 1
    assert batch.sources[0] == {
        "source": "chinanews_life",
        "status": "redirect",
        "http_status": 302,
    }
    assert batch.sources[1]["status"] == "http_error"
    assert "PRIVATE_UPSTREAM_BODY" not in str(batch)
    assert {str(r.url) for r in requests} == {feed[1] for feed in search.NEWS_FEEDS}
    assert all(r.url.scheme == "https" for r in requests)


@pytest.mark.parametrize(
    "body",
    [
        b"<html>not RSS</html>",
        b"<rss><channel>",
        b'<?xml version="1.0" encoding="unknown"?><rss><channel/></rss>',
        b'<!DOCTYPE rss [<!ENTITY a SYSTEM "file:///etc/passwd">]><rss><channel>&a;</channel></rss>',
        '<!DOCTYPE rss [<!ENTITY a "x">]><rss><channel>&a;</channel></rss>'.encode("utf-16"),
    ],
)
async def test_rejects_invalid_xml_dtd_entities_including_utf16(body):
    with pytest.raises(fetch.SourceFailure, match="format_error"):
        search.parse_feed(body, "固定媒体")


async def test_filters_dates_and_private_links_and_uses_beijing_for_local_dates():
    recent = (utcnow() - timedelta(hours=1)).astimezone(search.ZoneInfo("Asia/Shanghai"))
    rows = search.parse_feed(rss(date=recent.strftime("%Y-%m-%d %H:%M:%S")), "固定媒体")
    assert len(rows) == 1 and rows[0]["publisher"] == "固定媒体"
    for date in ["invalid", format_datetime(utcnow() - timedelta(days=9)), "2999-01-01"]:
        assert search.parse_feed(rss(date=date), "固定媒体") == []
    for url in [
        "http://127.0.0.1/a",
        "http://127.1/a",
        "http://0177.0.0.1/a",
        "http://169.254.169.254/latest",
        "http://[::1]/",
        "http://localhost/",
        "http://db.internal/",
        "http://user:pass@example.com/",
        "https://example.com:444/",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://[/",
    ]:
        assert not search.safe_url(url)
        assert search.parse_feed(rss(link=url), "固定媒体") == []


async def test_rejects_large_compressed_and_slow_responses(monkeypatch):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=b"x" * (fetch.MAX_BYTES + 1))
        )
    ) as client:
        with pytest.raises(fetch.SourceFailure, match="oversized"):
            await fetch.read_source(client, "https://example.com/feed")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, content=gzip.compress(b"x" * 10000), headers={"Content-Encoding": "gzip"}
            )
        )
    ) as client:
        with pytest.raises(fetch.SourceFailure, match="encoding_error"):
            await fetch.read_source(client, "https://example.com/feed")
    real_timeout = fetch.asyncio.timeout
    monkeypatch.setattr(fetch.asyncio, "timeout", lambda seconds: real_timeout(0.01))

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await fetch.asyncio.sleep(0.1)
            yield b"x"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=SlowStream()))
    ) as client:
        with pytest.raises(fetch.SourceFailure, match="timeout"):
            await fetch.read_source(client, "https://example.com/feed")


async def test_unavailable_sources_are_not_reported_as_empty_success(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(302, headers={"Location": "http://localhost"})
            )
        ),
    )
    with pytest.raises(search.NewsUnavailable):
        await search.search_news("水果")


async def test_diagnostics_only_keep_allowlisted_metadata():
    result = public_diagnostics(
        {
            "stage": "sources",
            "candidates": 3,
            "url": "SECRET",
            "body": "SECRET",
            "sources": [
                {
                    "source": "foodmate",
                    "status": "http_error",
                    "http_status": 503,
                    "body": "SECRET",
                    "url": "SECRET",
                },
                {"source": "unknown SECRET", "status": "ok"},
                {"source": [], "status": {}},
            ],
        }
    )
    assert result == {
        "stage": "sources",
        "candidates": 3,
        "sources": [{"source": "foodmate", "status": "http_error", "http_status": 503}],
    }
    assert "SECRET" not in str(result)
    assert public_diagnostics({"stage": [], "sources": "SECRET"}) == {"sources": []}
