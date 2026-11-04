"""邮件内容和发送器（不会真正连接邮件服务器）。"""

import logging

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.mail import (
    ConsoleMailSender,
    MailMessage,
    MemoryMailSender,
    SmtpMailSender,
    create_mail_sender,
    send_safely,
)
from app.mail import sender as sender_module
from app.mail.templates import password_reset_email, verification_email

LINK = "https://example.com/verify-email?token=abc&x=<1>"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_verification_email():
    mail = verification_email("a@example.com", LINK, 24)
    assert mail.to == "a@example.com"
    assert "验证" in mail.subject
    assert LINK in mail.text
    assert "24 小时" in mail.text
    # HTML 中的链接经过转义，防止注入
    assert "&amp;x=&lt;1&gt;" in mail.html
    assert "<1>" not in mail.html


def test_password_reset_email():
    mail = password_reset_email("a@example.com", LINK, 60)
    assert "重置密码" in mail.subject
    assert "60 分钟" in mail.text
    assert "退出登录" in mail.text


def _smtp_sender(port: int = 465) -> SmtpMailSender:
    return SmtpMailSender(
        host="smtp.example.com",
        port=port,
        username="sender@mail.example.com",
        password="secret",
        from_address="sender@mail.example.com",
        from_name="商业罗盘",
    )


def test_build_email_message():
    email = _smtp_sender().build(MailMessage("to@example.com", "主题", "正文", "<p>正文</p>"))
    assert email["Subject"] == "主题"
    assert email["To"] == "to@example.com"
    sender = email["From"].addresses[0]
    assert sender.display_name == "商业罗盘"
    assert sender.addr_spec == "sender@mail.example.com"
    assert email["Message-ID"].endswith("@mail.example.com>")
    assert {part.get_content_type() for part in email.iter_parts()} == {"text/plain", "text/html"}


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context = host, port, context
        self.calls: list[str] = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}")

    def send_message(self, message):
        self.calls.append(f"send:{message['To']}")


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(sender_module.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(sender_module.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


@pytest.mark.anyio
async def test_smtp_port_465_uses_ssl(fake_smtp):
    await _smtp_sender(465).send(MailMessage("to@example.com", "主题", "正文"))
    (smtp,) = fake_smtp.instances
    assert smtp.context is not None  # SMTP_SSL 带加密上下文
    assert smtp.calls == ["login:sender@mail.example.com", "send:to@example.com"]


@pytest.mark.anyio
async def test_other_ports_use_starttls(fake_smtp):
    await _smtp_sender(80).send(MailMessage("to@example.com", "主题", "正文"))
    (smtp,) = fake_smtp.instances
    assert smtp.calls[0] == "starttls"


@pytest.mark.anyio
async def test_send_safely_logs_failures_with_masked_address(caplog):
    class Broken:
        async def send(self, message):
            raise ConnectionError("smtp down")

    with caplog.at_level(logging.ERROR, logger="app.mail.sender"):
        await send_safely(Broken(), MailMessage("chestnut@example.com", "主题", "正文"))
    assert "c***@example.com" in caplog.text
    assert "chestnut@example.com" not in caplog.text


@pytest.mark.anyio
async def test_memory_sender():
    sender = MemoryMailSender()
    await sender.send(MailMessage("a@example.com", "s", "t"))
    assert len(sender.outbox) == 1


def test_create_mail_sender():
    console = Settings(_env_file=None, mail_backend="console")
    assert isinstance(create_mail_sender(console), ConsoleMailSender)
    smtp = Settings(
        _env_file=None,
        mail_backend="smtp",
        smtp_user="u@example.com",
        smtp_password=SecretStr("p"),
        mail_from="u@example.com",
    )
    sender = create_mail_sender(smtp)
    assert isinstance(sender, SmtpMailSender)
    assert sender.host == "smtpdm.aliyun.com"
    assert sender.port == 465
