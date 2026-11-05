"""数据库锁保护每天配额与单用户并发；请求 UUID 防止重复消费和写入。"""

from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.config import Settings
from app.db.base import utcnow
from app.db.models import AIRun, User


async def reserve(
    db, user, profile_id: UUID, request_id: UUID, kind: str, data: dict, settings: Settings
):
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    previous = await db.scalar(
        select(AIRun).where(AIRun.user_id == user.id, AIRun.request_id == request_id)
    )
    if previous:
        if previous.profile_id != profile_id or previous.kind != kind or previous.input != data:
            raise HTTPException(409, "同一个请求编号不能用于不同内容")
        if previous.status == "running" and previous.lease_until < utcnow():
            previous.status = "failed"
            previous.error = "服务曾中断，已保存的数字会保留；请重新发送"
            previous.finished_at = utcnow()
        await db.commit()
        return previous, False
    await db.execute(
        update(AIRun)
        .where(AIRun.user_id == user.id, AIRun.status == "running", AIRun.lease_until < utcnow())
        .values(status="failed", error="服务中断，请重新发送", finished_at=utcnow())
    )
    active = await db.scalar(
        select(AIRun.id).where(AIRun.user_id == user.id, AIRun.status == "running").limit(1)
    )
    if active:
        raise HTTPException(409, "上一条 AI 请求仍在处理，请先等待或取消")
    start = datetime.combine(
        utcnow().astimezone(ZoneInfo("Asia/Shanghai")).date(), time.min, ZoneInfo("Asia/Shanghai")
    )
    count = await db.scalar(
        select(func.count())
        .select_from(AIRun)
        .where(AIRun.user_id == user.id, AIRun.created_at >= start)
    )
    if count >= (
        user.daily_ai_quota if user.daily_ai_quota is not None else settings.ai_daily_quota
    ):
        raise HTTPException(429, "今天的 AI 次数已用完，明天再继续；手工测算仍可使用")
    run = AIRun(
        user_id=user.id,
        profile_id=profile_id,
        request_id=request_id,
        kind=kind,
        input=data,
        model=settings.report_model if kind == "report" else settings.interview_model,
        lease_until=utcnow() + timedelta(seconds=settings.ai_run_seconds + 30),
    )
    db.add(run)
    await db.flush()
    await db.commit()
    return run, True


async def update_run(factory, run_id, **values):
    async with factory() as db:
        await db.execute(
            update(AIRun).where(AIRun.id == run_id, AIRun.status == "running").values(**values)
        )
        await db.commit()


async def check_cancel(factory, run_id):
    async with factory() as db:
        run = await db.get(AIRun, run_id)
        if run.cancel_requested or run.status != "running":
            raise RunCancelled()


class RunCancelled(Exception):
    pass
