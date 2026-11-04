"""密码规则和哈希。

哈希使用 Argon2id（目前主流的密码哈希算法）。计算一次约几十毫秒、占用较多内存，
这是故意的：让别人拿到数据库后也很难暴力破解。为了不卡住其他请求，计算放在线程里执行。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 8
MAX_LENGTH = 128

_hasher = PasswordHasher()


class WeakPasswordError(ValueError):
    """密码不符合规则。错误信息可以直接展示给用户。"""


@lru_cache
def _common_passwords() -> frozenset[str]:
    path = Path(__file__).with_name("common_passwords.txt")
    lines = path.read_text(encoding="utf-8").splitlines()
    return frozenset(
        line.strip().lower() for line in lines if line.strip() and not line.startswith("#")
    )


def check_password_strength(password: str, email: str | None = None) -> None:
    """检查新密码是否符合规则，不符合时抛出 WeakPasswordError。

    规则（文档第四节）：至少 8 位；拒绝常见弱密码；不强制要求大小写、符号组合。
    """
    if len(password) < MIN_LENGTH:
        raise WeakPasswordError(f"密码至少需要 {MIN_LENGTH} 位")
    if len(password) > MAX_LENGTH:
        raise WeakPasswordError(f"密码不能超过 {MAX_LENGTH} 位")
    lowered = password.lower()
    # 只由一两种字符组成的密码（如 11111111、abababab）也算太简单
    if lowered in _common_passwords() or len(set(lowered)) <= 2:
        raise WeakPasswordError("这个密码太常见，容易被猜到，请换一个")
    if email:
        email = email.lower()
        if lowered in {email, email.partition("@")[0]}:
            raise WeakPasswordError("密码不能和邮箱相同")


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("dummy-password-for-equal-timing")


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    return await anyio.to_thread.run_sync(_verify, password_hash, password)


async def burn_verify_time(password: str) -> None:
    """邮箱不存在时也做一次同样耗时的校验，避免别人通过响应快慢判断邮箱是否注册过。"""
    await anyio.to_thread.run_sync(_verify, _dummy_hash(), password)


def needs_rehash(password_hash: str) -> bool:
    """哈希参数升级后，用户下次登录时自动用新参数重新哈希。"""
    return _hasher.check_needs_rehash(password_hash)
