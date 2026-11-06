"""完整请求的字节预算；测试替身与真实provider使用同一入口。"""

from fastapi import HTTPException

from app.resources import json_size, reserve_input


def fit_messages(messages, tools, limit):
    messages = list(messages)
    # 只丢弃完整历史轮次；当前轮含工具调用时绝不拆分协议。
    while json_size({"messages": messages, "tools": tools}) > limit:
        users = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(users) < 2:
            raise HTTPException(422, "本次AI资料超过输入上限，请缩短资料或开始新对话")
        start, end = users[0], users[1]
        messages = (
            messages[:start]
            + [m for m in messages[start:end] if m["role"] == "system"]
            + messages[end:]
        )
    return messages


class AccountProvider:
    def __init__(self, provider, factory, settings, user_id):
        self.provider, self.factory, self.settings, self.user_id = (
            provider,
            factory,
            settings,
            user_id,
        )

    async def complete(self, messages, tools=None, **kwargs):
        messages = fit_messages(messages, tools, self.settings.ai_input_max_bytes)
        size = json_size({"messages": messages, "tools": tools})

        async def charge():
            await reserve_input(self.factory, self.user_id, size, self.settings)

        await charge()
        return await self.provider.complete(messages, tools, before_retry=charge, **kwargs)
