"""写入速率与输入边界；不依赖前端或AI自觉遵守。"""

import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.db.base import utcnow
from app.db.models import AIInputReservation, ProfileWrite


def json_size(value):
    return len(json.dumps(value, ensure_ascii=False, default=str).encode())


def validate_document(value, previous=None):
    size = json_size(value)
    if size > 256 * 1024 and (previous is None or size >= json_size(previous)):
        raise HTTPException(422, "单份档案最多256KiB，请缩短备注或拆分方案")

    def visit(node, key="", old=None):
        if old is not None and node == old:
            return
        if (
            isinstance(node, str)
            and len(node) > (1000 if key == "note" else 2000)
            and not (isinstance(old, str) and len(node) < len(old))
        ):
            raise HTTPException(422, "备注最多1000字，其他文本最多2000字")
        if isinstance(node, list):
            if len(node) > 200 and not (isinstance(old, list) and len(node) <= len(old)):
                raise HTTPException(422, "单个集合最多200项")
            for i, item in enumerate(node):
                visit(item, old=old[i] if isinstance(old, list) and i < len(old) else None)
        if isinstance(node, dict):
            if (len(node) > 100 and not (isinstance(old, dict) and len(node) <= len(old))) or any(
                len(str(k)) > 80 and (not isinstance(old, dict) or k not in old) for k in node
            ):
                raise HTTPException(422, "字段数量或名称过长")
            for k, v in node.items():
                visit(v, k, old.get(k) if isinstance(old, dict) else None)

    # 兼容旧数据的缩减操作；新增或修改的内容仍需通过边界检查。
    for k, v in value.items():
        if previous is None or v != previous.get(k):
            visit(v, k, previous.get(k) if previous else None)
    proposition = value.get("value_proposition", {})
    if len(proposition) > 20 and (
        previous is None or len(proposition) > len(previous.get("value_proposition", {}))
    ):
        raise HTTPException(422, "价值主张最多20个字段")


async def reserve_write(db, user_id):
    settings = db.info.get("settings") or get_settings()
    async with async_sessionmaker(db.bind, expire_on_commit=False)() as reservation:
        await reservation.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"profile_write:{user_id}"},
        )
        for since, limit in (
            (utcnow() - timedelta(minutes=1), settings.profile_writes_per_minute),
            (utcnow() - timedelta(days=1), settings.profile_writes_per_day),
        ):
            count = await reservation.scalar(
                select(func.count())
                .select_from(ProfileWrite)
                .where(ProfileWrite.user_id == user_id, ProfileWrite.created_at >= since)
            )
            if count >= limit:
                raise HTTPException(429, "档案修改次数已达上限，请稍后再试")
        reservation.add(ProfileWrite(user_id=user_id))
        await reservation.commit()


async def reserve_input(factory, user_id, size, settings):
    if size > settings.ai_input_max_bytes:
        raise HTTPException(422, "本次AI资料超过输入上限，请缩短资料或开始新对话")
    async with factory() as db:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"ai_input:{user_id}"},
        )
        start = datetime.combine(
            utcnow().astimezone(ZoneInfo("Asia/Shanghai")).date(),
            time.min,
            ZoneInfo("Asia/Shanghai"),
        )
        used = await db.scalar(
            select(func.coalesce(func.sum(AIInputReservation.size), 0)).where(
                AIInputReservation.user_id == user_id, AIInputReservation.created_at >= start
            )
        )
        if used + size > settings.ai_input_daily_bytes:
            raise HTTPException(429, "今天的AI输入额度已用完，请明天再试")
        db.add(AIInputReservation(user_id=user_id, size=size))
        await db.commit()
