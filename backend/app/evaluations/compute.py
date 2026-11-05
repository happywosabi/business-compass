"""独立进程执行纯计算；数据库协调跨API进程并发与账号预算。"""

import asyncio
import multiprocessing
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.db.base import utcnow
from app.db.models import CalculationRun, User
from app.engine import CheckRules
from app.templates.registry import calculate, parse_parameters, preview


def _worker(connection, params, rules, changes):
    try:
        key = "orchard" if params.get("schema_version") == 2 else "physical_store"
        params = parse_parameters(key, params)
        rules = CheckRules.model_validate(rules) if rules else None
        result = calculate(params, rules) if changes is None else preview(params, changes)
        connection.send((True, (type(result), result.model_dump(mode="json"))))
    except (ValueError, KeyError) as error:
        connection.send((False, str(error)[:500]))
    finally:
        connection.close()


async def _isolated(params, rules, changes, seconds, *, target=_worker):
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    # Pydantic的动态泛型不能跨spawn pickle；边界只传普通数据。
    params = params.model_dump(mode="json") if params is not None else None
    rules = rules.model_dump(mode="json") if rules is not None else None
    process = context.Process(target=target, args=(writer, params, rules, changes), daemon=True)
    try:
        process.start()
        writer.close()
        # Pipe收发在专用线程中进行，避免大结果的IPC读写阻塞事件循环。
        async with asyncio.timeout(seconds):
            while not reader.poll():
                if not process.is_alive() and not reader.poll():
                    raise HTTPException(503, "测算进程异常退出，请稍后重试")
                await asyncio.sleep(0.01)
            ok, result = await asyncio.to_thread(reader.recv)
        if not ok:
            raise ValueError(result)
        result_type, data = result
        return result_type.model_validate(data)
    except TimeoutError as error:
        raise HTTPException(503, "测算超时，请减少方案规模后重试") from error
    except (EOFError, OSError) as error:
        raise HTTPException(503, "测算进程异常退出，请稍后重试") from error
    finally:
        if process.pid:
            if process.is_alive():
                process.kill()
            await asyncio.to_thread(process.join)
        reader.close()
        writer.close()


async def compute(db, user_id, params, rules=None, changes=None):
    settings = db.info.get("settings") or get_settings()
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as budget:
        # 一个用户同时只能占一个计算槽；锁与独立预算事务都不依赖业务提交。
        if not await budget.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"calculation:{user_id}"},
        ):
            raise HTTPException(429, "已有测算正在处理，请稍后重试")
        slot = False
        for i in range(2):
            if await budget.scalar(
                text("SELECT pg_try_advisory_xact_lock(9412280, :slot)"), {"slot": i}
            ):
                slot = True
                break
        if not slot:
            raise HTTPException(503, "测算繁忙，请稍后重试")
        async with factory() as reservation:
            if await reservation.get(User, user_id) is None:
                raise HTTPException(401, "请先登录")
            now = utcnow()
            start = datetime.combine(
                now.astimezone(ZoneInfo("Asia/Shanghai")).date(),
                time.min,
                ZoneInfo("Asia/Shanghai"),
            )
            for since, limit in (
                (now - timedelta(minutes=1), settings.calculation_per_minute),
                (start, settings.calculation_per_day),
            ):
                count = await reservation.scalar(
                    select(func.count())
                    .select_from(CalculationRun)
                    .where(CalculationRun.user_id == user_id, CalculationRun.created_at >= since)
                )
                if count >= limit:
                    raise HTTPException(429, "测算次数已达上限，请稍后再试")
            reservation.add(CalculationRun(user_id=user_id))
            await reservation.commit()
        return await _isolated(params, rules, changes, settings.calculation_seconds)
