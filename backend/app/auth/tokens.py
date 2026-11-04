"""随机令牌：用于登录会话、验证邮箱、重置密码。

令牌原文只交给用户（Cookie 或邮件链接），数据库只存 SHA-256 哈希值。
这样即使数据库泄露，别人也无法用里面的数据登录或重置密码。
"""

from __future__ import annotations

import hashlib
import secrets


def new_token() -> str:
    """生成一个 43 个字符的随机令牌（256 位随机数）。"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
