"""受限资讯读取：调用方只传固定来源或运维配置，不跟随链接。"""

import asyncio

import httpx

MAX_BYTES = 1_000_000


class SourceFailure(ValueError):
    def __init__(self, code: str, http_status: int | None = None):
        self.code = code
        self.http_status = http_status
        super().__init__(code)


async def read_source(client: httpx.AsyncClient, url: str) -> bytes:
    try:
        async with asyncio.timeout(15):
            async with client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "BusinessCompass/1.0",
                    "Accept": "application/rss+xml, application/xml, application/json, text/xml",
                    "Accept-Encoding": "identity",
                },
                follow_redirects=False,
            ) as response:
                if 300 <= response.status_code < 400:
                    raise SourceFailure("redirect", response.status_code)
                if response.status_code != 200:
                    raise SourceFailure("http_error", response.status_code)
                # 不接收压缩内容，避免解压缩放大；按实际传输内容逐块限制大小。
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise SourceFailure("encoding_error")
                length = response.headers.get("content-length", "")
                if length.isdecimal() and int(length) > MAX_BYTES:
                    raise SourceFailure("oversized")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_BYTES:
                        raise SourceFailure("oversized")
                    body.extend(chunk)
                return bytes(body)
    except (TimeoutError, httpx.TimeoutException) as error:
        raise SourceFailure("timeout") from error
    except httpx.HTTPError as error:
        raise SourceFailure("network_error") from error
