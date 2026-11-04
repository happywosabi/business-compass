"""健康检查：Docker 和监控用来判断服务是否正常。"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.deps import DB

logger = logging.getLogger(__name__)

router = APIRouter(tags=["系统"])


@router.get("/api/health", summary="健康检查")
async def health(db: DB):
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("健康检查：数据库连接失败")
        return JSONResponse(status_code=503, content={"status": "error", "database": "error"})
    return {"status": "ok", "database": "ok"}
