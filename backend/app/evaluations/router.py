from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.db.models import Evaluation
from app.deps import DB
from app.engine import PhysicalStoreParams, WhatIfResult
from app.engine.params import ALL_KEYS
from app.profiles import service as profiles

from . import service
from .schemas import ApplyWhatIf, EvaluationCreate, EvaluationLabel, EvaluationOut, WhatIfRequest

router = APIRouter(prefix="/api/profiles/{profile_id}", tags=["测算"])


@router.post("/evaluations", response_model=EvaluationOut, status_code=201)
async def create(profile_id: UUID, body: EvaluationCreate, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    return await service.create_evaluation(db, profile, body.revision, label=body.label)


@router.get("/evaluations", response_model=list[EvaluationOut])
async def history(
    profile_id: UUID,
    db: DB,
    user: CurrentUser,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await profiles.get_owned_profile(db, user.id, profile_id)
    return list(
        await db.scalars(
            select(Evaluation)
            .where(Evaluation.profile_id == profile_id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationOut)
async def detail(profile_id: UUID, evaluation_id: UUID, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    return await service.get_snapshot(db, profile, evaluation_id)


@router.patch("/evaluations/{evaluation_id}", response_model=EvaluationOut)
async def label(
    profile_id: UUID, evaluation_id: UUID, body: EvaluationLabel, db: DB, user: CurrentUser
):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    item = await service.get_snapshot(db, profile, evaluation_id)
    item.label = body.label
    await db.commit()
    return item


@router.post("/what-if", response_model=WhatIfResult)
async def preview(profile_id: UUID, body: WhatIfRequest, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    return await service.try_changes(db, profile, body.changes, body.evaluation_id, body.revision)


@router.post("/what-if/apply", response_model=EvaluationOut, status_code=201)
async def apply(profile_id: UUID, body: ApplyWhatIf, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    snapshot = await service.get_snapshot(db, profile, body.evaluation_id)
    await service.try_changes(db, profile, body.changes, body.evaluation_id, body.revision)
    # 老报告上的试算以老报告完整参数为基准，确认应用时也保持同一基准。
    restored = PhysicalStoreParams.model_validate(snapshot.parameters).with_values(body.changes)
    for key in body.changes:
        value = restored.get(key)
        if value:
            restored = restored.with_values({key: {**value.model_dump(), "source": "user"}})
    changes = {k: restored.get(k) for k in ALL_KEYS}
    profile = await profiles.edit_parameters(
        db,
        profile,
        body.revision,
        changes,
        source="snapshot_apply",
        reason="应用历史快照上的试算方案",
        commit=False,
    )
    return await service.create_evaluation(
        db, profile, profile.revision, trigger="parameter_change"
    )
