"""单实例定时任务：到期档案删除、可选热点采集。失败记录类型，不输出密钥。"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, text

from app.config import Settings
from app.content.hot import collect
from app.db.base import utcnow
from app.db.models import Profile
from app.db.session import create_engine, create_session_factory
from app.llm.provider import DeepSeekProvider
from app.logs import setup_logging
from app.profiles.service import RESTORE_DAYS

logger = logging.getLogger(__name__)


async def purge(db):
    result = await db.execute(
        delete(Profile).where(Profile.deleted_at <= utcnow() - timedelta(days=RESTORE_DAYS))
    )
    await db.commit()
    return result.rowcount


async def main():
    setup_logging()
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url())
    factory = create_session_factory(engine)
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
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
