"""邮件发送器。

- SmtpMailSender：通过 SMTP 真实发送（阿里云邮件推送）
- ConsoleMailSender：只写到日志，不真正发送（本机开发用）
- MemoryMailSender：存在内存里（测试用，测试可以读取邮件内容）
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

import anyio

from app.config import Settings
from app.logs import mask_email

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


class MailSender(Protocol):
    async def send(self, message: MailMessage) -> None: ...


class SmtpMailSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        from_name: str,
        timeout: int = 15,
    ):
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.from_address = from_address
        self.from_name = from_name
        self.timeout = timeout

    def build(self, message: MailMessage) -> EmailMessage:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = Address(display_name=self.from_name, addr_spec=self.from_address)
        email["To"] = message.to
        email["Date"] = formatdate(localtime=True)
        email["Message-ID"] = make_msgid(domain=self.from_address.partition("@")[2] or None)
        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")
        return email

    def _send_blocking(self, email: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.port == 465:
            # 465 端口：一开始就用 SSL 加密连接
            with smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout, context=context
            ) as smtp:
                smtp.login(self.username, self._password)
                smtp.send_message(email)
        else:
            # 其他端口：先建立普通连接，再升级为加密连接
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.starttls(context=context)
                smtp.login(self.username, self._password)
                smtp.send_message(email)

    async def send(self, message: MailMessage) -> None:
        # smtplib 是阻塞的，放到线程里执行，避免卡住其他请求
        await anyio.to_thread.run_sync(self._send_blocking, self.build(message))
        logger.info("邮件已发送：%s「%s」", mask_email(message.to), message.subject)


class ConsoleMailSender:
    async def send(self, message: MailMessage) -> None:
        logger.info(
            "【未真正发送的邮件】收件人：%s\n主题：%s\n\n%s",
            message.to,
            message.subject,
            message.text,
        )


class MemoryMailSender:
    def __init__(self) -> None:
        self.outbox: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.outbox.append(message)


async def send_safely(sender: MailSender, message: MailMessage) -> None:
    """发送邮件；失败时只记录日志，不影响已经返回给用户的结果。"""
    try:
        await sender.send(message)
    except Exception:
        logger.exception("邮件发送失败：%s「%s」", mask_email(message.to), message.subject)


def create_mail_sender(settings: Settings) -> MailSender:
    if settings.mail_backend == "console":
        return ConsoleMailSender()
    return SmtpMailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
        from_address=settings.mail_from,
        from_name=settings.mail_from_name,
        timeout=settings.smtp_timeout_seconds,
    )
