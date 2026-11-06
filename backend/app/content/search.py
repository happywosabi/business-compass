"""固定公开 RSS 来源；只读取摘要，不访问模型、用户或来源提供的网址。"""

import asyncio
import html
import ipaddress
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from app.db.base import utcnow

from .fetch import SourceFailure, read_source

logger = logging.getLogger(__name__)

# 固定 HTTPS 端点，不接受请求参数、模型输出或 RSS 链接指定新的抓取地址。
NEWS_FEEDS = (
    ("chinanews_life", "https://www.chinanews.com.cn/rss/life.xml", "中新网·生活"),
    ("chinanews_finance", "https://www.chinanews.com.cn/rss/finance.xml", "中新网·财经"),
    ("chinanews_latest", "https://www.chinanews.com.cn/rss/scroll-news.xml", "中新网·即时"),
    ("foodmate", "https://news.foodmate.net/rss.php", "食品伙伴网"),
)


@dataclass
class NewsBatch:
    rows: list[dict]
    sources: list[dict]


class NewsUnavailable(ValueError):
    pass


def safe_url(url: str | None) -> bool:
    try:
        if not isinstance(url, str) or len(url) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
            return False
        parsed = urlparse(str(url))
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and parsed.port in {None, 80, 443}
        )
        if not valid:
            return False
        host = parsed.hostname.rstrip(".").lower()
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)) and (
                "." in host
                and not host.split(".")[-1].isdigit()
                and not host.endswith((".localhost", ".local", ".internal"))
            )
    except ValueError:
        return False


def plain(value: str, limit: int = 1000) -> str:
    # 不跨越嵌套的 <，避免未闭合标签反复扫描造成二次方耗时。
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^<>]*>", "", value))).strip()[:limit]


def article_url(link: str) -> str:
    try:
        parsed = urlparse(link)
    except ValueError:
        return ""
    if parsed.hostname in {"www.bing.com", "bing.com"} and parsed.path == "/news/apiclick.aspx":
        link = parse_qs(parsed.query).get("url", [link])[0]
    return link if safe_url(link) else ""


def parse_feed(body: bytes, publisher: str) -> list[dict]:
    try:
        root = ET.fromstring(body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ET.ParseError, DefusedXmlException, ValueError, LookupError) as error:
        raise SourceFailure("format_error") from error
    if root.tag != "rss" or root.find("channel") is None:
        raise SourceFailure("format_error")
    now, rows = utcnow(), []
    for item in root.findall(".//item")[:50]:
        title = plain(item.findtext("title", ""), 250)
        link = article_url(item.findtext("link", ""))
        try:
            date = item.findtext("pubDate", "").strip()
            try:
                published = parsedate_to_datetime(date)
            except (ValueError, TypeError):
                published = datetime.fromisoformat(date)
            if published.tzinfo is None:
                published = published.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            published = published.astimezone(UTC)
        except (ValueError, TypeError, IndexError, OverflowError):
            continue
        if (
            not title
            or not link
            or not now - timedelta(days=7) <= published <= now + timedelta(hours=1)
        ):
            continue
        rows.append(
            {
                "title": title,
                "url": link,
                "excerpt": plain(item.findtext("description", "")),
                "published_at": published.isoformat(),
                "retrieved_at": now.isoformat(),
                "publisher": publisher,
                "kind": "news_summary",
            }
        )
    return rows


async def load_news() -> NewsBatch:
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:

        async def one(source: str, url: str, publisher: str):
            try:
                rows = parse_feed(await read_source(client, url), publisher)
                return rows, {"source": source, "status": "ok", "items": len(rows)}
            except SourceFailure as error:
                diagnostic = {"source": source, "status": error.code}
                if error.http_status is not None:
                    diagnostic["http_status"] = error.http_status
                logger.warning("News source unavailable: %s %s", source, error.code)
                return [], diagnostic

        results = await asyncio.gather(*(one(*feed) for feed in NEWS_FEEDS))
    rows = {row["url"]: row for group, _ in results for row in group}
    return NewsBatch(
        sorted(rows.values(), key=lambda row: row["published_at"], reverse=True),
        [diagnostic for _, diagnostic in results],
    )


async def search_news(query: str) -> list[dict]:
    batch = await load_news()
    if not any(source["status"] == "ok" for source in batch.sources):
        raise NewsUnavailable("资讯来源均不可用")
    words = [word for word in query[:250].split() if word]
    return [
        row
        for row in batch.rows
        if any(word in row["title"] + row["excerpt"] for word in words)
        or related(query, row["title"])
    ][:30]


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
