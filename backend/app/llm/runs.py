"""数据库锁保护每天配额与单用户并发；请求 UUID 防止重复消费和写入。"""

from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.config import Settings
from app.db.base import utcnow
from app.db.models import AIRun, User

MAX_CONCURRENT_RUNS = 3


async def reserve(
    db, user, profile_id: UUID, request_id: UUID, kind: str, data: dict, settings: Settings
):
    user = await db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if user.status != "active" or user.deleted_at is not None:
        raise HTTPException(403, "账号已停用")
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
    active = list(
        await db.scalars(select(AIRun).where(AIRun.user_id == user.id, AIRun.status == "running"))
    )
    for item in active:
        if kind == item.kind == "interview" and item.profile_id == profile_id:
            raise HTTPException(409, "这份档案的上一条访谈仍在处理，请先等待或取消")
        if kind == item.kind == "report" and item.input == data:
            # 同一快照跨页面/标签页恢复已有任务，不重复扣配额或替换生成中的报告。
            await db.commit()
            return item, False
    if len(active) >= MAX_CONCURRENT_RUNS:
        raise HTTPException(409, "已有 3 个 AI 任务正在处理，请等待其中一个完成或取消后再试")
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
        user = await db.get(User, run.user_id) if run else None
        if (
            run is None
            or run.cancel_requested
            or run.status != "running"
            or user is None
            or user.status != "active"
            or user.deleted_at
        ):
            raise RunCancelled()


class RunCancelled(Exception):
    pass


async def guard_write(db, run_id):
    """与停用操作争用用户行锁，防止检查后再落入写入竞态。"""
    owner_id = await db.scalar(select(AIRun.user_id).where(AIRun.id == run_id))
    user = await db.scalar(
        select(User)
        .where(User.id == owner_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    run = await db.scalar(
        select(AIRun)
        .where(AIRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or user.status != "active"
        or user.deleted_at
        or run is None
        or run.status != "running"
        or run.cancel_requested
    ):
        raise RunCancelled()
    return run
