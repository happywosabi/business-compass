import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select

from app.auth.dependencies import CurrentUser, VerifiedUser
from app.db.base import utcnow
from app.db.models import AIRun, Conversation, Message
from app.deps import DB, AppSettings
from app.llm.runs import reserve
from app.profiles import service as profiles
from app.profiles.schemas import StrictBody

from .service import drive

router = APIRouter(prefix="/api/profiles/{profile_id}/interview", tags=["AI访谈"])


class Send(StrictBody):
    request_id: UUID
    revision: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=2000)


async def expire(db, run):
    if run.status == "running" and run.lease_until < utcnow():
        run.status = "failed"
        run.error = "服务曾中断，已记录的数字会保留，请重新发送"
        run.finished_at = utcnow()
        await db.commit()
    return run


def run_out(run):
    return {
        "id": str(run.id),
        "request_id": str(run.request_id),
        "status": run.status,
        "output": run.output,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
    }


async def owned_run(db, user_id, profile_id, run_id):
    await profiles.get_owned_profile(db, user_id, profile_id)
    run = await db.scalar(
        select(AIRun).where(
            AIRun.id == run_id, AIRun.user_id == user_id, AIRun.profile_id == profile_id
        )
    )
    if run is None:
        raise HTTPException(404, "找不到这条请求")
    return await expire(db, run)


@router.get("")
async def history(profile_id: UUID, db: DB, user: CurrentUser):
    await profiles.get_owned_profile(db, user.id, profile_id)
    conv = await db.scalar(select(Conversation).where(Conversation.profile_id == profile_id))
    runs = list(
        await db.scalars(
            select(AIRun)
            .where(AIRun.profile_id == profile_id, AIRun.kind == "interview")
            .order_by(AIRun.created_at.desc())
            .limit(50)
        )
    )
    for run in runs:
        await expire(db, run)
    rows = []
    if conv and runs:
        rows = list(
            await db.scalars(
                select(Message)
                .where(Message.run_id.in_([r.id for r in runs]))
                .order_by(Message.created_at, Message.ordinal)
            )
        )
    return {
        "messages": [
            {
                "id": str(m.id),
                "run_id": str(m.run_id),
                "role": m.payload["role"],
                "content": m.payload.get("content") or "",
                "tool_calls": bool(m.payload.get("tool_calls")),
            }
            for m in rows
            if m.payload["role"] in {"user", "assistant"}
        ],
        "runs": [run_out(r) for r in reversed(runs)],
    }


@router.post("/messages")
async def send(
    profile_id: UUID,
    body: Send,
    request: Request,
    db: DB,
    settings: AppSettings,
    user: VerifiedUser,
):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    if not body.content.strip():
        raise HTTPException(422, "请输入想说的话")
    if not settings.deepseek_api_key.get_secret_value() and settings.app_env != "test":
        raise HTTPException(503, "AI 尚未配置，可以先在档案中填写数字")
    run, created = await reserve(
        db,
        user,
        profile.id,
        body.request_id,
        "interview",
        body.model_dump(mode="json", exclude={"request_id"}),
        settings,
    )
    hub = request.app.state.ai_hub
    queue = asyncio.Queue(maxsize=256)
    hub.listeners.setdefault(run.id, set()).add(queue)
    if created:
        hub.start(run.id, drive(request.app, run.id))

    async def events():
        def event(name, data):
            return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            yield event("run", run_out(run))
            if not created:
                yield event("resume", run_out(run))
                return
            while True:
                try:
                    name, data = await asyncio.wait_for(queue.get(), 15)
                    yield event(name, data)
                    if name in {"done", "error"}:
                        break
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            hub.listeners.get(run.id, set()).discard(queue)
            if not hub.listeners.get(run.id):
                hub.listeners.pop(run.id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}")
async def status(profile_id: UUID, run_id: UUID, db: DB, user: CurrentUser):
    return run_out(await owned_run(db, user.id, profile_id, run_id))


@router.post("/runs/{run_id}/cancel")
async def cancel(profile_id: UUID, run_id: UUID, request: Request, db: DB, user: CurrentUser):
    run = await owned_run(db, user.id, profile_id, run_id)
    run.cancel_requested = True
    await db.commit()
    task = request.app.state.ai_hub.tasks.get(run.id)
    if task and not task.done():
        task.cancel()
    return run_out(run)
