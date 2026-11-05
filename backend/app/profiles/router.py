"""商业档案接口。所有子资源先通过统一的所有权检查。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.db.base import utcnow
from app.db.models import ParameterChange
from app.deps import DB

from . import service
from .schemas import (
    ChangeOut,
    DefaultRequest,
    ParametersUpdate,
    ProfileCopy,
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
    RevisionBody,
    TemplateOut,
)

router = APIRouter(prefix="/api", tags=["商业档案"])


@router.get("/templates", response_model=list[TemplateOut])
async def templates(user: CurrentUser):
    return [service.template_info()]


@router.get("/profiles", response_model=list[ProfileOut])
async def profiles(
    db: DB, user: CurrentUser, view: Literal["active", "archived", "deleted"] = "active"
):
    return [service.profile_out(p) for p in await service.list_profiles(db, user.id, view)]


@router.post("/profiles", response_model=ProfileOut, status_code=201)
async def create(body: ProfileCreate, db: DB, user: CurrentUser):
    return service.profile_out(await service.create_profile(db, user.id, body))


@router.get("/profiles/{profile_id}", response_model=ProfileOut)
async def detail(profile_id: UUID, db: DB, user: CurrentUser):
    return service.profile_out(await service.get_owned_profile(db, user.id, profile_id))


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
async def edit(profile_id: UUID, body: ProfileUpdate, db: DB, user: CurrentUser):
    profile = await service.get_owned_profile(db, user.id, profile_id)
    profile = await service.write_profile(
        db, profile, body.revision, body.model_dump(exclude_unset=True, exclude={"revision"})
    )
    await db.commit()
    return service.profile_out(profile)


@router.patch("/profiles/{profile_id}/parameters", response_model=ProfileOut)
async def parameters(profile_id: UUID, body: ParametersUpdate, db: DB, user: CurrentUser):
    profile = await service.get_owned_profile(db, user.id, profile_id)
    return service.profile_out(
        await service.edit_parameters(db, profile, body.revision, body.changes, reason=body.reason)
    )


@router.post("/profiles/{profile_id}/defaults", response_model=ProfileOut)
async def defaults(profile_id: UUID, body: DefaultRequest, db: DB, user: CurrentUser):
    profile = await service.get_owned_profile(db, user.id, profile_id)
    return service.profile_out(await service.use_defaults(db, profile, body.revision, body.keys))


@router.get("/profiles/{profile_id}/changes", response_model=list[ChangeOut])
async def changes(
    profile_id: UUID,
    db: DB,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await service.get_owned_profile(db, user.id, profile_id)
    return list(
        await db.scalars(
            select(ParameterChange)
            .where(ParameterChange.profile_id == profile_id)
            .order_by(ParameterChange.created_at.desc(), ParameterChange.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/profiles/{profile_id}/copy", response_model=ProfileOut, status_code=201)
async def copy(profile_id: UUID, body: ProfileCopy, db: DB, user: CurrentUser):
    profile = await service.get_owned_profile(db, user.id, profile_id)
    return service.profile_out(await service.copy_profile(db, profile, body.revision, body.name))


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete(profile_id: UUID, revision: int, db: DB, user: CurrentUser):
    profile = await service.get_owned_profile(db, user.id, profile_id)
    await service.write_profile(db, profile, revision, {"deleted_at": utcnow()})
    await db.commit()
    return Response(status_code=204)


@router.post("/profiles/{profile_id}/restore", response_model=ProfileOut)
async def restore(profile_id: UUID, body: RevisionBody, db: DB, user: CurrentUser):
    profile = await service.get_owned_profile(db, user.id, profile_id, deleted=True)
    profile = await service.write_profile(
        db, profile, body.revision, {"deleted_at": None}, deleted=True
    )
    await db.commit()
    return service.profile_out(profile)
