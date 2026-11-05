"""档案所有权、乐观并发控制与参数审计的唯一写入入口。"""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import ParameterChange, Profile
from app.engine import PhysicalStoreParams
from app.engine.params import ALL_KEYS
from app.templates import load_template

from .schemas import FieldOut, IndustryOut, ProfileCreate, ProfileOut, TemplateOut

RESTORE_DAYS = 30


def template_info() -> TemplateOut:
    template = load_template()
    schema = PhysicalStoreParams.model_json_schema()
    definitions = schema["$defs"]

    def resolve(item):
        return definitions[item["$ref"].rsplit("/", 1)[-1]] if "$ref" in item else item

    fields = []
    for spec in template.specs.values():
        section, name = spec.key.split(".")
        section_schema = resolve(schema["properties"][section])
        param_schema = resolve(section_schema["properties"][name]["anyOf"][0])
        fields.append(
            FieldOut(**spec.model_dump(), value_schema=param_schema["properties"]["base"])
        )
    return TemplateOut(
        key=template.key,
        version=template.version,
        label="实体小店",
        industries=[
            IndustryOut(code=k, label=template.industry(k).label) for k in template.industry_codes
        ],
        fields=fields,
        definitions=definitions,
    )


async def get_owned_profile(
    db: AsyncSession, user_id: UUID, profile_id: UUID, *, deleted: bool = False
) -> Profile:
    query = select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
    if deleted:
        query = query.where(Profile.deleted_at > utcnow() - timedelta(days=RESTORE_DAYS))
    else:
        query = query.where(Profile.deleted_at.is_(None))
    profile = await db.scalar(query.execution_options(populate_existing=True))
    if profile is None:
        raise HTTPException(404, "找不到这个档案")
    return profile


def profile_out(profile: Profile) -> ProfileOut:
    template = load_template(profile.template_key)
    params = PhysicalStoreParams.model_validate(profile.parameters)
    stale = []
    for key, rule in template.industry(profile.industry).derived.items():
        value, reference = params.get(key), params.get(rule.ratio_of)
        if value and reference and value.source == "default":
            if abs(value.base - round(reference.base * rule.ratio, 2)) > 0.01:
                stale.append(key)
    data = {
        name: getattr(profile, name)
        for name in ProfileOut.model_fields
        if name not in {"quick_missing", "derived_stale_keys"}
    }
    return ProfileOut(
        **data, quick_missing=template.quick_missing(params), derived_stale_keys=stale
    )


async def list_profiles(db: AsyncSession, user_id: UUID, view: str) -> list[Profile]:
    query = select(Profile).where(Profile.user_id == user_id)
    if view == "deleted":
        query = query.where(Profile.deleted_at > utcnow() - timedelta(days=RESTORE_DAYS))
    else:
        query = query.where(Profile.deleted_at.is_(None))
        query = query.where(
            Profile.status == "archived" if view == "archived" else Profile.status != "archived"
        )
    return list(await db.scalars(query.order_by(Profile.updated_at.desc(), Profile.id)))


def record_changes(
    db: AsyncSession,
    profile: Profile,
    before: PhysicalStoreParams,
    after: PhysicalStoreParams,
    *,
    source: str,
    reason: str | None = None,
    message_id: UUID | None = None,
) -> None:
    for key in ALL_KEYS:
        old, new = before.get(key), after.get(key)
        if old != new:
            db.add(
                ParameterChange(
                    profile_id=profile.id,
                    profile_revision=profile.revision,
                    parameter_key=key,
                    old_value=old.model_dump(mode="json") if old else None,
                    new_value=new.model_dump(mode="json") if new else None,
                    source=source,
                    reason=reason,
                    message_id=message_id,
                )
            )


def user_parameters(params: PhysicalStoreParams) -> PhysicalStoreParams:
    """公开的手工编辑接口不能伪造默认值、实验或真实数据来源。"""
    return params.with_values(
        {
            key: {**value.model_dump(mode="json"), "source": "user"}
            for key in ALL_KEYS
            if (value := params.get(key)) is not None
        }
    )


async def create_profile(db: AsyncSession, user_id: UUID, body: ProfileCreate) -> Profile:
    template = load_template(body.template_key)
    if body.industry not in template.industry_codes:
        raise HTTPException(422, "目前支持饮品店，其他业态正在准备中")
    params = user_parameters(body.parameters)
    profile = Profile(
        user_id=user_id,
        template_version=template.version,
        **body.model_dump(exclude={"parameters"}),
        parameters=params.model_dump(mode="json"),
    )
    db.add(profile)
    await db.flush()
    record_changes(
        db, profile, PhysicalStoreParams(), params, source="user_edit", reason="新建档案"
    )
    await db.commit()
    return profile


async def write_profile(
    db: AsyncSession,
    profile: Profile,
    revision: int,
    values: dict[str, Any],
    *,
    deleted: bool = False,
) -> Profile:
    """单条条件 UPDATE 是并发裁决点；调用方提交事务及审计记录。"""
    condition = Profile.deleted_at.is_not(None) if deleted else Profile.deleted_at.is_(None)
    result = await db.execute(
        update(Profile)
        .where(
            Profile.id == profile.id,
            Profile.user_id == profile.user_id,
            Profile.revision == revision,
            condition,
        )
        .values(**values, revision=Profile.revision + 1, updated_at=utcnow())
        .returning(Profile)
        .execution_options(populate_existing=True)
    )
    changed = result.scalar_one_or_none()
    if changed is None:
        await db.rollback()
        raise HTTPException(409, "档案已在其他页面更新，请刷新后再保存；你的输入还在")
    return changed


async def edit_parameters(
    db: AsyncSession,
    profile: Profile,
    revision: int,
    changes: dict[str, Any],
    *,
    source: str = "user_edit",
    reason: str | None = None,
    message_id: UUID | None = None,
    commit: bool = True,
) -> Profile:
    before = PhysicalStoreParams.model_validate(profile.parameters)
    try:
        after = before.with_values(changes)
    except (KeyError, ValidationError) as error:
        detail = str(error).split("For further information", 1)[0][:1200]
        raise HTTPException(422, f"参数不符合要求：{detail}") from error
    if source == "user_edit":
        after = after.with_values(
            {
                key: {**value.model_dump(mode="json"), "source": "user"}
                for key in changes
                if (value := after.get(key)) is not None
            }
        )
    profile = await write_profile(
        db, profile, revision, {"parameters": after.model_dump(mode="json")}
    )
    record_changes(db, profile, before, after, source=source, reason=reason, message_id=message_id)
    if commit:
        await db.commit()
    return profile


async def use_defaults(
    db: AsyncSession, profile: Profile, revision: int, keys: list[str]
) -> Profile:
    template = load_template(profile.template_key)
    before = PhysicalStoreParams.model_validate(profile.parameters)
    try:
        cleared = before.with_values(dict.fromkeys(keys))
        filled, _ = template.fill_defaults(cleared, profile.industry)
        changes = {}
        for key in keys:
            value = filled.get(key)
            if value is None:
                raise HTTPException(422, f"{template.specs[key].label}没有可用默认值，请先填写")
            changes[key] = value
    except KeyError as error:
        raise HTTPException(422, "包含未知参数") from error
    return await edit_parameters(
        db, profile, revision, changes, source="default", reason="用户确认使用默认值"
    )


async def copy_profile(
    db: AsyncSession, profile: Profile, revision: int, name: str | None
) -> Profile:
    # 条件更新同时保护复制基准，复制不改动原档案的修订号和内容。
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
        raise HTTPException(409, "档案已经更新，请刷新后再复制")
    new = Profile(
        user_id=current.user_id,
        name=name or f"{current.name[:75]}（副本）",
        template_key=current.template_key,
        template_version=current.template_version,
        industry=current.industry,
        city=current.city,
        district=current.district,
        stage=current.stage,
        status="draft",
        opened_on=current.opened_on,
        value_proposition=deepcopy(current.value_proposition),
        parameters=deepcopy(current.parameters),
        brand_voice=deepcopy(current.brand_voice),
    )
    db.add(new)
    await db.flush()
    record_changes(
        db,
        new,
        PhysicalStoreParams(),
        PhysicalStoreParams.model_validate(new.parameters),
        source="user_edit",
        reason="从现有档案复制",
    )
    await db.commit()
    return new
