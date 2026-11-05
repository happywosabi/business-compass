"""测算事务：锁定同一修订、补默认值并记录、计算和保存不可变快照。"""

from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Evaluation, Profile
from app.engine import PhysicalStoreParams, evaluate, what_if
from app.profiles import service as profiles
from app.templates import load_template


def summary(result) -> str:
    base = result.scenarios["base"]
    if base.steady_monthly_cash <= 0:
        return "按目前的估计，生意稳定后仍在亏钱，建议先调整方案。"
    if base.payback_month is None:
        return "按目前的估计，10 年内收不回投入。"
    return f"按目前的估计，第 {base.payback_month} 个月收回投入；" + (
        "在租约期限内。" if base.lease_check == "pass" else "已超过租约期限，需要重新评估。"
    )


async def get_snapshot(db: AsyncSession, profile: Profile, evaluation_id: UUID) -> Evaluation:
    item = await db.scalar(
        select(Evaluation).where(
            Evaluation.id == evaluation_id, Evaluation.profile_id == profile.id
        )
    )
    if item is None:
        raise HTTPException(404, "找不到这份测算结果")
    return item


async def create_evaluation(
    db: AsyncSession,
    profile: Profile,
    revision: int,
    *,
    label: str | None = None,
    trigger: str = "user_request",
    commit: bool = True,
) -> Evaluation:
    # 锁与乐观 revision 一起使用，保证参数、审计、快照来自同一个工作稿。
    current = await db.scalar(
        select(Profile)
        .where(
            Profile.id == profile.id,
            Profile.user_id == profile.user_id,
            Profile.deleted_at.is_(None),
            Profile.revision == revision,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None:
        raise HTTPException(409, "档案已更新，请刷新后再测算")
    template = load_template(current.template_key)
    params = PhysicalStoreParams.model_validate(current.parameters)
    missing = template.quick_missing(params)
    if missing:
        names = "、".join(template.specs[k].label for k in missing)
        raise HTTPException(422, f"先填写这些数字再算：{names}")
    filled, _ = template.fill_defaults(params, current.industry)
    if filled.missing_keys():
        raise HTTPException(422, "部分数字还未填写，且没有可用默认值")
    profile = await profiles.write_profile(
        db,
        current,
        revision,
        {
            "parameters": filled.model_dump(mode="json"),
            "template_version": template.version,
            "status": "active" if current.status != "archived" else "archived",
        },
    )
    profiles.record_changes(db, profile, params, filled, source="default", reason="测算前补齐缺项")
    result = evaluate(filled, template.check_rules(profile.industry))
    item = Evaluation(
        profile_id=profile.id,
        profile_revision=profile.revision,
        trigger=trigger,
        label=label,
        template_key=template.key,
        template_version=template.version,
        engine_version=result.engine_version,
        parameters=filled.model_dump(mode="json"),
        results=result.model_dump(mode="json"),
        summary=summary(result),
    )
    db.add(item)
    await db.flush()
    if commit:
        await db.commit()
    return item


async def try_changes(
    db: AsyncSession, profile: Profile, changes: dict, evaluation_id: UUID | None, revision: int
):
    if profile.revision != revision:
        raise HTTPException(409, "档案已更新，请刷新后再试")
    params = profile.parameters
    if evaluation_id:
        params = (await get_snapshot(db, profile, evaluation_id)).parameters
    try:
        return what_if(PhysicalStoreParams.model_validate(params), changes)
    except (KeyError, ValidationError, ValueError) as error:
        raise HTTPException(
            422, f"无法试算，请检查参数是否齐全和有效：{str(error)[:800]}"
        ) from error
