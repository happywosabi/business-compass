"""邮件内容。每封邮件都有纯文本和 HTML 两个版本。"""

from __future__ import annotations

from html import escape

from .sender import MailMessage

_FOOTER_TEXT = "如果这不是你本人的操作，请忽略这封邮件。\n\n商业罗盘"


def _html(paragraphs: list[str], link: str, button: str) -> str:
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    safe_link = escape(link, quote=True)
    return (
        '<div style="font-family:sans-serif;font-size:15px;line-height:1.6;color:#222">'
        f"{body}"
        f'<p><a href="{safe_link}" style="display:inline-block;padding:10px 20px;'
        f'background:#2563eb;color:#fff;text-decoration:none;border-radius:6px">{escape(button)}</a></p>'
        f'<p style="color:#666;font-size:13px">如果按钮无法点击，请复制下面的链接到浏览器打开：<br>{safe_link}</p>'
        '<p style="color:#666;font-size:13px">如果这不是你本人的操作，请忽略这封邮件。</p>'
        "<p>商业罗盘</p></div>"
    )


def verification_email(to: str, link: str, valid_hours: int) -> MailMessage:
    lines = ["你好！", f"请点击下面的按钮验证你的邮箱，链接 {valid_hours} 小时内有效。"]
    return MailMessage(
        to=to,
        subject="【商业罗盘】请验证你的邮箱",
        text="\n\n".join(lines) + f"\n\n{link}\n\n{_FOOTER_TEXT}",
        html=_html(lines, link, "验证邮箱"),
    )


def password_reset_email(to: str, link: str, valid_minutes: int) -> MailMessage:
    lines = [
        "你好！",
        f"我们收到了重置密码的请求。请点击下面的按钮设置新密码，链接 {valid_minutes} 分钟内有效。",
        "重置成功后，所有已登录的设备都会退出登录。",
    ]
    return MailMessage(
        to=to,
        subject="【商业罗盘】重置密码",
        text="\n\n".join(lines) + f"\n\n{link}\n\n{_FOOTER_TEXT}",
        html=_html(lines, link, "重置密码"),
    )
