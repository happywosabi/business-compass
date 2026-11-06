"""单实例定时任务：到期档案删除、可选热点采集。失败记录类型，不输出密钥。"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert

from app.config import Settings
from app.content.hot import collect
from app.db.base import utcnow
from app.db.models import (
    AdminAudit,
    AIInputReservation,
    PendingAction,
    Profile,
    ProfileWrite,
    WorkerHeartbeat,
)
from app.db.session import create_engine, create_session_factory
from app.llm.provider import DeepSeekProvider
from app.logs import setup_logging
from app.profiles.service import RESTORE_DAYS

logger = logging.getLogger(__name__)


async def purge(db):
    result = await db.execute(
        delete(Profile).where(Profile.deleted_at <= utcnow() - timedelta(days=RESTORE_DAYS))
    )
    for model in (ProfileWrite, AIInputReservation):
        await db.execute(delete(model).where(model.created_at < utcnow() - timedelta(days=2)))
    await db.execute(
        delete(PendingAction).where(PendingAction.expires_at < utcnow() - timedelta(days=7))
    )
    await db.execute(
        delete(AdminAudit).where(AdminAudit.created_at < utcnow() - timedelta(days=180))
    )
    await db.commit()
    return result.rowcount


async def heartbeat(factory):
    while True:
        try:
            async with factory() as db:
                await db.execute(
                    insert(WorkerHeartbeat)
                    .values(name="main", seen_at=utcnow())
                    .on_conflict_do_update(
                        index_elements=[WorkerHeartbeat.name], set_={"seen_at": utcnow()}
                    )
                )
                await db.commit()
        except Exception as error:
            logger.warning("Worker heartbeat failed: %s", type(error).__name__)
        await asyncio.sleep(60)


async def main():
    setup_logging()
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url())
    factory = create_session_factory(engine)
    heartbeat_task = asyncio.create_task(heartbeat(factory))
    try:
        while True:
            # session级 advisory lock 限制多个 worker 实例同时采集。
            async with engine.connect() as connection:
                locked = await connection.scalar(text("SELECT pg_try_advisory_lock(9412271)"))
                if locked:
                    try:
                        async with factory() as db:
                            count = await purge(db)
                            logger.info("Expired profiles removed: %d", count)
                        await collect(factory, settings, DeepSeekProvider(settings))
                    except Exception as error:
                        logger.warning("Worker iteration failed: %s", type(error).__name__)
                    finally:
                        await connection.execute(text("SELECT pg_advisory_unlock(9412271)"))
            await asyncio.sleep(max(60, settings.worker_interval_seconds))
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
