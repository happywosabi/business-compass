"""DeepSeek 的兼容接口；重试只发生在收到响应前，工具写入不在重试范围。"""

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx

from app.config import Settings


class LLMUnavailable(Exception):
    pass


class DeepSeekProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        thinking: bool | None = None,
        max_tokens: int | None = None,
        attempts: int = 2,
    ):
        settings = self.settings
        if not settings.deepseek_api_key.get_secret_value():
            raise LLMUnavailable("AI 尚未配置，可以先在档案中填写数字")
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": settings.ai_report_max_tokens
            if model == settings.report_model
            else settings.ai_max_output_tokens,
        }
        if tools:
            body["tools"] = tools
        if max_tokens is not None:
            body["max_tokens"] = min(max_tokens, body["max_tokens"])
        # 短访谈和已有确定性数字的报告无需消耗隐藏思考预算。
        if thinking is not None or model == settings.interview_model:
            body["thinking"] = {"type": "enabled" if thinking else "disabled"}
        for attempt in range(attempts):
            received = False
            finished = False
            content, reasoning, calls, usage = "", "", {}, {}
            try:
                async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                    async with client.stream(
                        "POST",
                        settings.deepseek_base_url.rstrip("/") + "/chat/completions",
                        headers={
                            "Authorization": "Bearer "
                            + settings.deepseek_api_key.get_secret_value()
                        },
                        json=body,
                    ) as response:
                        if (
                            response.status_code in {429, 500, 502, 503, 504}
                            and attempt + 1 < attempts
                        ):
                            await asyncio.sleep(0.5)
                            continue
                        if response.status_code >= 400:
                            raise LLMUnavailable("AI 服务暂时不可用，请稍后重试")
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if raw == "[DONE]":
                                break
                            data = json.loads(raw)
                            received = True
                            if data.get("usage"):
                                usage = data["usage"]
                            for choice in data.get("choices", []):
                                delta = choice.get("delta", {})
                                reasoning += delta.get("reasoning_content") or ""
                                piece = delta.get("content") or ""
                                content += piece
                                if piece and on_delta:
                                    await on_delta(piece)
                                for item in delta.get("tool_calls") or []:
                                    current = calls.setdefault(
                                        item["index"],
                                        {
                                            "id": "",
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        },
                                    )
                                    current["id"] += item.get("id") or ""
                                    current["function"]["name"] += (
                                        item.get("function", {}).get("name") or ""
                                    )
                                    current["function"]["arguments"] += (
                                        item.get("function", {}).get("arguments") or ""
                                    )
                                if choice.get("finish_reason") in {"stop", "tool_calls"}:
                                    finished = True
                                if choice.get("finish_reason") == "length":
                                    raise LLMUnavailable(
                                        "回复过长，请缩短问题后重试；已记录的数字会保留"
                                    )
                if not finished:
                    raise LLMUnavailable("回复连接中断，请稍后恢复对话")
                message = {"role": "assistant", "content": content or None}
                if reasoning:
                    message["reasoning_content"] = reasoning
                if calls:
                    message["tool_calls"] = [calls[k] for k in sorted(calls)]
                if not content and not calls:
                    raise LLMUnavailable("AI 没有返回内容，请稍后重试")
                return message, usage
            except (httpx.HTTPError, json.JSONDecodeError) as error:
                if received or attempt + 1 >= attempts:
                    raise LLMUnavailable("AI 连接中断，已记录的数字会保留，请重试") from error
                await asyncio.sleep(0.5)
        raise LLMUnavailable("AI 服务暂时不可用")
