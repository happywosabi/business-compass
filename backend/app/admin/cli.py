"""服务端授权：uv run python -m app.admin.cli grant EMAIL --reason '原因'。"""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.config import Settings
from app.db.models import AdminAudit, User, UserSession
from app.db.session import create_engine, create_session_factory

from .access import management_lock


async def set_admin(db, email, granted, reason):
    await management_lock(db)
    user = await db.scalar(
        select(User)
        .where(User.email == email.strip().lower(), User.deleted_at.is_(None))
        .with_for_update()
    )
    if user is None:
        raise ValueError("找不到这个账号")
    if granted and (not user.email_verified_at or user.status != "active"):
        raise ValueError("只能授权已验证邮箱且正常启用的账号")
    if not granted and user.is_admin and user.status == "active":
        count = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.is_admin.is_(True),
                User.status == "active",
                User.deleted_at.is_(None),
                User.email_verified_at.is_not(None),
            )
        )
        if count <= 1:
            raise ValueError("必须保留一个可用管理员")
    old = user.is_admin
    user.is_admin = granted
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.add(
        AdminAudit(
            actor_id=None,
            action="role.grant" if granted else "role.revoke",
            target=str(user.id),
            reason=reason,
            ip=None,
            changes={"before": old, "after": granted, "via": "server_cli"},
        )
    )
    await db.commit()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["grant", "revoke"])
    parser.add_argument("email")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if not 5 <= len(args.reason.strip()) <= 300:
        parser.error("原因需为5–300字")
    engine = create_engine(Settings().sqlalchemy_url())
    try:
        async with create_session_factory(engine)() as db:
            await set_admin(db, args.email, args.action == "grant", args.reason.strip())
        print("管理员权限已更新；该账号所有会话已撤销，请重新登录。")
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
