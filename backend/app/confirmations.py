"""模型只提出动作；账户拥有者确认后执行，修订绑定、过期和幂等由服务端保证。"""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.db.base import utcnow
from app.db.budgets import lock_usage
from app.db.models import PendingAction, Profile
from app.deps import DB
from app.profiles import service as profiles
from app.profiles.schemas import StrictBody

router = APIRouter(prefix="/api/profiles/{profile_id}/confirmations", tags=["动作确认"])


def out(item):
    return {
        "id": str(item.id),
        "action": item.action,
        "revision": item.revision,
        "payload": item.payload,
        "expires_at": item.expires_at.isoformat(),
        "result": item.result,
    }


async def propose(db, profile, action, payload=None):
    item = PendingAction(
        user_id=profile.user_id,
        profile_id=profile.id,
        revision=profile.revision,
        action=action,
        payload=payload or {},
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.add(item)
    await db.flush()
    return out(item)


@router.get("")
async def pending(profile_id: UUID, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    rows = await db.scalars(
        select(PendingAction)
        .where(
            PendingAction.profile_id == profile.id,
            PendingAction.user_id == user.id,
            PendingAction.revision == profile.revision,
            PendingAction.expires_at > utcnow(),
            PendingAction.result.is_(None),
        )
        .order_by(PendingAction.created_at.desc())
        .limit(5)
    )
    return [out(item) for item in rows]


class Confirm(StrictBody):
    revision: int


@router.post("/{action_id}/confirm")
async def confirm(profile_id: UUID, action_id: UUID, body: Confirm, db: DB, user: CurrentUser):
    from app.evaluations import service as evaluations
    from app.evaluations.router import apply_changes
    from app.evaluations.schemas import ApplyWhatIf

    await lock_usage(db, user.id)
    item = await db.scalar(
        select(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.user_id == user.id,
            PendingAction.profile_id == profile_id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "找不到这项操作")
    if item.result is not None:
        return item.result
    profile = await db.scalar(
        select(Profile)
        .where(
            Profile.id == profile_id,
            Profile.user_id == user.id,
            Profile.deleted_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if profile is None:
        raise HTTPException(404, "找不到这个档案")
    if item.expires_at <= utcnow():
        raise HTTPException(409, "确认已过期，请重新提出操作")
    if profile.revision != item.revision or body.revision != item.revision:
        raise HTTPException(409, "档案已更新，请重新确认")
    if item.action == "evaluation":
        result = await evaluations.create_evaluation(
            db, profile, item.revision, trigger="interview", commit=False
        )
        item.result = {"evaluation_id": str(result.id)}
    elif item.action == "defaults":
        await profiles.use_defaults(db, profile, item.revision, item.payload["keys"], commit=False)
        item.result = {"revision": profile.revision}
    elif item.action == "apply" and "evaluation_id" not in item.payload:
        profile = await profiles.edit_parameters(
            db,
            profile,
            item.revision,
            item.payload["changes"],
            source="snapshot_apply",
            reason="用户点击确认应用试算方案",
            commit=False,
        )
        result = await evaluations.create_evaluation(
            db, profile, profile.revision, trigger="parameter_change", commit=False
        )
        item.result = {"evaluation_id": str(result.id)}
    elif item.action == "apply":
        result = await apply_changes(
            db, profile, ApplyWhatIf(revision=item.revision, **item.payload), commit=False
        )
        item.result = {"evaluation_id": str(result.id)}
    else:
        raise HTTPException(422, "不支持的确认操作")
    await db.commit()
    return item.result
