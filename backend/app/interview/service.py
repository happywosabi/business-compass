"""浏览器断开只停止订阅；消息与运行状态持久化，工具不自动重放。"""

import asyncio
import json
import logging
import time
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.db.base import utcnow
from app.db.models import AIRun, Conversation, Message
from app.llm.runs import RunCancelled, check_cancel, update_run
from app.profiles import service as profiles

from . import tools

logger = logging.getLogger(__name__)

PROMPT_VERSION = "interview-1"
PROMPT = Path(__file__).with_name("prompt.md").read_text()


class Coordinator:
    def __init__(self):
        self.tasks: dict[UUID, asyncio.Task] = {}
        self.listeners: dict[UUID, set[asyncio.Queue]] = {}

    async def emit(self, run_id, event, data):
        for queue in tuple(self.listeners.get(run_id, set())):
            if queue.full():
                self.listeners[run_id].discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(("error", {"message": "连接太慢，请恢复对话查看完整结果"}))
            else:
                queue.put_nowait((event, data))

    def start(self, run_id, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def conversation(db, profile_id):
    item = await db.scalar(select(Conversation).where(Conversation.profile_id == profile_id))
    if item is None:
        item = Conversation(profile_id=profile_id)
        db.add(item)
        await db.flush()
    return item


async def history_context(db, conversation_id):
    run_ids = list(
        await db.scalars(
            select(AIRun.id)
            .join(Message, Message.run_id == AIRun.id)
            .where(Message.conversation_id == conversation_id, AIRun.status == "succeeded")
            .group_by(AIRun.id)
            .order_by(AIRun.created_at.desc())
            .limit(20)
        )
    )
    if not run_ids:
        return []
    rows = await db.scalars(
        select(Message)
        .where(Message.run_id.in_(run_ids))
        .order_by(Message.created_at, Message.ordinal)
    )
    return [m.payload for m in rows]


async def drive(app, run_id: UUID):
    settings, factory, hub = app.state.settings, app.state.session_factory, app.state.ai_hub
    try:
        async with asyncio.timeout(settings.ai_run_seconds):
            async with factory() as db:
                run = await db.get(AIRun, run_id)
                profile = await profiles.get_owned_profile(db, run.user_id, run.profile_id)
                if profile.revision != run.input["revision"]:
                    raise HTTPException(409, "档案已更新，请确认最新数字后重新发送")
                conv = await conversation(db, profile.id)
                previous = await history_context(db, conv.id)
                user_message = Message(
                    conversation_id=conv.id,
                    run_id=run_id,
                    ordinal=0,
                    payload={"role": "user", "content": run.input["content"]},
                    prompt_version=PROMPT_VERSION,
                )
                db.add(user_message)
                await db.commit()
                specs = tools.template_prompt()
                messages = [
                    {
                        "role": "system",
                        "content": PROMPT + "\n参数定义：" + json.dumps(specs, ensure_ascii=False),
                    },
                    *previous,
                    {
                        "role": "system",
                        "content": "当前档案及待问清单："
                        + json.dumps(tools.state(profile), ensure_ascii=False),
                    },
                    user_message.payload,
                ]
                expected_revision, ordinal = profile.revision, 1
                usage_in, usage_out, last_extra = 0, 0, {}
                for round_number in range(6):
                    await check_cancel(factory, run_id)

                    last_cancel_check = 0.0

                    async def delta(piece):
                        nonlocal last_cancel_check
                        if time.monotonic() - last_cancel_check > 1:
                            await check_cancel(factory, run_id)
                            last_cancel_check = time.monotonic()
                        await hub.emit(run_id, "delta", {"text": piece})

                    message, usage = await app.state.llm.complete(
                        messages,
                        tools.definitions() if round_number < 5 else None,
                        model=run.model,
                        on_delta=delta,
                    )
                    usage_in += usage.get("prompt_tokens", 0)
                    usage_out += usage.get("completion_tokens", 0)
                    await update_run(
                        factory, run_id, input_tokens=usage_in, output_tokens=usage_out
                    )
                    await check_cancel(factory, run_id)
                    row = Message(
                        conversation_id=conv.id,
                        run_id=run_id,
                        ordinal=ordinal,
                        payload=message,
                        prompt_version=PROMPT_VERSION,
                    )
                    db.add(row)
                    await db.flush()
                    ordinal += 1
                    messages.append(message)
                    calls = message.get("tool_calls") or []
                    if not calls:
                        await db.commit()
                        output = {"content": message.get("content") or "", **last_extra}
                        await update_run(
                            factory, run_id, status="succeeded", output=output, finished_at=utcnow()
                        )
                        await hub.emit(run_id, "done", output)
                        return
                    if round_number >= 5 or len(calls) > 12:
                        raise ValueError("工具调用次数过多，请拆成几条消息")
                    for call in calls:
                        await check_cancel(factory, run_id)
                        await hub.emit(run_id, "status", {"text": "正在核对并记下数字…"})
                        try:
                            async with db.begin_nested():
                                profile = await profiles.get_owned_profile(
                                    db, run.user_id, run.profile_id
                                )
                                profile, output = await tools.execute(
                                    db,
                                    profile,
                                    call["function"]["name"],
                                    json.loads(call["function"]["arguments"]),
                                    expected_revision,
                                    row.id,
                                )
                                expected_revision = profile.revision
                        except (HTTPException, ValidationError, ValueError, KeyError) as error:
                            output = {
                                "error": error.detail
                                if isinstance(error, HTTPException)
                                else str(error)[:1000]
                            }
                        reply = {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(output, ensure_ascii=False),
                        }
                        db.add(
                            Message(
                                conversation_id=conv.id,
                                run_id=run_id,
                                ordinal=ordinal,
                                payload=reply,
                                prompt_version=PROMPT_VERSION,
                            )
                        )
                        ordinal += 1
                        messages.append(reply)
                        await db.commit()
                        last_extra.update(
                            {
                                k: v
                                for k, v in output.items()
                                if k in {"quick_replies", "evaluation_id"}
                            }
                        )
                        await hub.emit(run_id, "profile", output)
                    await hub.emit(run_id, "replace", {"text": ""})
    except (Exception, asyncio.CancelledError) as error:
        logger.info("AI run %s ended: %s", run_id, type(error).__name__)
        cancelled = isinstance(error, (RunCancelled, asyncio.CancelledError))
        detail = (
            "已取消。已经记下的数字会保留。"
            if cancelled
            else (
                error.detail
                if isinstance(error, HTTPException)
                else "AI 暂时无法继续，已记下的数字会保留，请重试"
            )
        )
        await update_run(
            factory,
            run_id,
            status="cancelled" if cancelled else "failed",
            error=detail,
            finished_at=utcnow(),
        )
        await hub.emit(run_id, "error", {"message": detail})
