import json

import httpx
import pytest

from app.config import Settings
from app.llm.provider import DeepSeekProvider, LLMUnavailable

pytestmark = pytest.mark.anyio


async def test_stream_merges_tool_fragments_and_usage(monkeypatch):
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {
                                    "name": "update_parameters",
                                    "arguments": '{"changes":',
                                },
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{}}"}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 10}},
    ]

    def handler(request):
        body = json.loads(request.content)
        assert body["thinking"]["type"] == "disabled"
        return httpx.Response(
            200, text="\n\n".join("data: " + json.dumps(c) for c in chunks) + "\n\ndata: [DONE]\n\n"
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    provider = DeepSeekProvider(Settings(_env_file=None, deepseek_api_key="test-key"))
    message, usage = await provider.complete(
        [{"role": "user", "content": "测试"}], model="deepseek-flash"
    )
    assert message["tool_calls"][0]["function"] == {
        "name": "update_parameters",
        "arguments": '{"changes":{}}',
    }
    assert usage["prompt_tokens"] == 20


async def test_stream_without_completion_does_not_accept_partial_reply(monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, text='data: {"choices":[{"delta":{"content":"部分内容"}}]}\n\n'
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport))
    with pytest.raises(LLMUnavailable, match="连接中断"):
        await DeepSeekProvider(Settings(_env_file=None, deepseek_api_key="test-key")).complete(
            [], model="deepseek-flash"
        )


async def test_report_can_disable_hidden_thinking_to_bound_generation_time(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-pro"
        assert body["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"先核实报价"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    provider = DeepSeekProvider(Settings(_env_file=None, deepseek_api_key="test-key"))
    message, _ = await provider.complete([], model="deepseek-v4-pro", thinking=False)
    assert message["content"] == "先核实报价"
