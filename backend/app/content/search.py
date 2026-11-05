"""限定端点的在线资讯检索；只读取 RSS 摘要，不访问模型或用户提供的网址。"""

import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

import httpx

from app.db.base import utcnow

NEWS_ENDPOINT = "https://www.bing.com/news/search"
MAX_BYTES = 1_000_000


def safe_url(url: str | None) -> bool:
    try:
        parsed = urlparse(str(url))
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def plain(value: str, limit: int = 1000) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", value))).strip()[:limit]


def article_url(link: str) -> str:
    parsed = urlparse(link)
    if parsed.hostname in {"www.bing.com", "bing.com"} and parsed.path == "/news/apiclick.aspx":
        link = parse_qs(parsed.query).get("url", [link])[0]
    return link if safe_url(link) else ""


async def search_news(query: str) -> list[dict]:
    # 固定公共搜索端点，不跟随重定向；链接仅用于来源展示，不在服务器抓取。
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        async with client.stream(
            "GET",
            NEWS_ENDPOINT,
            params={
                "q": query[:250],
                "format": "rss",
                "setlang": "zh-cn",
                "qft": 'interval="7"',
            },
            headers={"User-Agent": "BusinessCompass/1.0"},
        ) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("资讯响应过大")
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("不支持的资讯格式")
    root = ET.fromstring(body)
    now, rows = utcnow(), []
    for item in root.findall(".//item")[:50]:
        title = plain(item.findtext("title", ""), 250)
        link = article_url(item.findtext("link", ""))
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", ""))
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
        except (ValueError, TypeError, IndexError):
            continue
        if (
            not title
            or not link
            or not now - timedelta(days=7) <= published <= now + timedelta(hours=1)
        ):
            continue
        publisher = next((el.text for el in item if el.tag.endswith("}Source")), "必应资讯")
        rows.append(
            {
                "title": title,
                "url": link,
                "excerpt": plain(item.findtext("description", "")),
                "published_at": published.isoformat(),
                "retrieved_at": now.isoformat(),
                "publisher": plain(publisher or "必应资讯", 100),
                "kind": "news_summary",
            }
        )
    return rows


def related(title: str, other: str) -> bool:
    words = re.sub(r"[\W_]", "", title.casefold())
    pairs = {words[i : i + 2] for i in range(len(words) - 1)}
    return bool(pairs) and sum(p in other.casefold() for p in pairs) / len(pairs) >= 0.45


async def research(topic: dict) -> dict:
    """每次写作重新检索选中热点，失败明确降级到可追溯快照。"""
    try:
        rows = await search_news(topic["title"])
        sources = [row for row in rows if related(topic["title"], row["title"])][:3]
        if sources and any(s["excerpt"] for s in sources):
            return {
                "status": "live",
                "sources": sources,
                "note": "已联网检索，依据来源摘要写作，未读取全文。",
            }
    except (httpx.HTTPError, ValueError, ET.ParseError):
        pass
    sources = topic["sources"]
    has_summary = any(s.get("kind") == "news_summary" and s.get("excerpt") for s in sources)
    return {
        "status": "cached" if has_summary else "title_only",
        "sources": sources,
        "note": "本次联网未取得新资料，使用选中时的资讯摘要与时间。"
        if has_summary
        else "本次联网未取得热点详情，现有来源仅提供标题，只关联话题，不补写新闻事实。",
    }
