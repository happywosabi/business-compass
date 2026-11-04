"""邮箱地址的处理规则。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def normalize_email(email: str) -> str:
    """统一转成小写、去掉首尾空格后再存储和比较。"""
    return email.strip().lower()


@lru_cache
def _disposable_domains() -> frozenset[str]:
    path = Path(__file__).with_name("disposable_domains.txt")
    lines = path.read_text(encoding="utf-8").splitlines()
    return frozenset(
        line.strip().lower() for line in lines if line.strip() and not line.startswith("#")
    )


def is_disposable(email: str) -> bool:
    """是否为一次性临时邮箱（包括其子域名，如 a.mailinator.com）。"""
    domain = normalize_email(email).rpartition("@")[2]
    parts = domain.split(".")
    candidates = {".".join(parts[i:]) for i in range(len(parts) - 1)}
    return bool(candidates & _disposable_domains())
