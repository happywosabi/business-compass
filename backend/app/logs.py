"""日志相关的小工具。"""

from __future__ import annotations

import logging


def setup_logging() -> None:
    """设置 app 下所有模块的日志输出格式（uvicorn 自己的日志不受影响）。"""
    logger = logging.getLogger("app")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def mask_email(email: str) -> str:
    """日志里给邮箱打码：chestnut@example.com → c***@example.com"""
    local, sep, domain = email.partition("@")
    if not sep:
        return "***"
    return f"{local[:1]}***@{domain}"
