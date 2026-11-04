"""登录相关的规则（不需要数据库）。"""

import pytest

from app.auth import passwords
from app.auth.email_rules import is_disposable, normalize_email
from app.auth.passwords import WeakPasswordError, check_password_strength
from app.auth.tokens import hash_token, new_token


@pytest.mark.parametrize(
    "password",
    ["correct-horse-42", "我的店2026开业啦", "Xk9#mP2q", "a" * 7 + "b" + "c"],
)
def test_acceptable_passwords(password):
    check_password_strength(password, "someone@example.com")


@pytest.mark.parametrize(
    ("password", "email", "reason"),
    [
        ("abc1234", None, "至少需要 8 位"),
        ("x" * 129, None, "不能超过 128 位"),
        ("12345678", None, "太常见"),
        ("QWERTY123", None, "太常见"),  # 不区分大小写
        ("woaini1314", None, "太常见"),
        ("abababab", None, "太常见"),  # 只有两种字符
        ("someone2026", "someone2026@example.com", "不能和邮箱相同"),
        ("someone2026@example.com", "someone2026@example.com", "不能和邮箱相同"),
    ],
)
def test_rejected_passwords(password, email, reason):
    with pytest.raises(WeakPasswordError, match=reason):
        check_password_strength(password, email)


@pytest.mark.anyio
async def test_hash_and_verify():
    hashed = await passwords.hash_password("correct-horse-42")
    assert hashed.startswith("$argon2id$")
    assert await passwords.verify_password(hashed, "correct-horse-42")
    assert not await passwords.verify_password(hashed, "wrong")
    assert not await passwords.verify_password("not-a-hash", "correct-horse-42")
    assert not passwords.needs_rehash(hashed)
    # 同一个密码每次哈希结果都不同（带随机盐）
    assert hashed != await passwords.hash_password("correct-horse-42")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_normalize_email():
    assert normalize_email("  Someone@Example.COM ") == "someone@example.com"


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("a@mailinator.com", True),
        ("a@sub.mailinator.com", True),
        ("a@YOPMAIL.com", True),
        ("a@gmail.com", False),
        ("a@qq.com", False),
        ("a@mailinator.com.cn", False),
    ],
)
def test_disposable_domains(email, expected):
    assert is_disposable(email) is expected


def test_tokens():
    token = new_token()
    assert len(token) == 43
    assert token != new_token()
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64
    assert hash_token(token) != token
