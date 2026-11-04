"""邮件发送。"""

from .sender import (
    ConsoleMailSender,
    MailMessage,
    MailSender,
    MemoryMailSender,
    SmtpMailSender,
    create_mail_sender,
    send_safely,
)

__all__ = [
    "ConsoleMailSender",
    "MailMessage",
    "MailSender",
    "MemoryMailSender",
    "SmtpMailSender",
    "create_mail_sender",
    "send_safely",
]
