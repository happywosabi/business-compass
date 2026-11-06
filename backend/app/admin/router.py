"""后台只提供明确的数据操作，不提供命令执行或服务器管理能力。"""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import defer, load_only

from app.auth.dependencies import CurrentSessionDep
from app.content.diagnostics import collection_error, public_diagnostics
from app.db.base import utcnow
from app.db.models import (
    AdminAudit,
    AIRun,
    CalculationRun,
    ContentDraft,
    Conversation,
    Evaluation,
    EvaluationReport,
    HotCollectionRun,
    HotTopic,
    Message,
    ParameterChange,
    Profile,
    ResourceUsage,
    User,
    UserSession,
    WorkerHeartbeat,
)
from app.deps import DB, AppSettings
from app.pagination import before, cursor_for
from app.profiles.schemas import StrictBody

from .access import Admin, admin_identity, audit, unlock

router = APIRouter(prefix="/api/admin", tags=["管理员"])
Limit = Query(20, ge=1, le=100)


class Unlock(StrictBody):
    password: str = Field(min_length=1, max_length=128)


class Reason(StrictBody):
    reason: str = Field(min_length=5, max_length=300)


class UserAction(Reason):
    action: Literal["disable", "enable", "unlock", "revoke_sessions", "quota"]
    expected: dict = Field(max_length=5)
    quota: int | None = Field(default=None, ge=0, le=1000)


class Hide(Reason):
    hidden: bool
    expected: bool


class Inspect(Reason):
    section: Literal["parameters", "history", "evaluations", "chat", "reports", "copy"]
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


def page(rows, limit, serialize, date="created_at"):
    return {
        "items": [serialize(r) for r in rows[:limit]],
        "next_cursor": cursor_for(getattr(rows[limit - 1], date), rows[limit - 1].id)
        if len(rows) > limit
        else None,
    }


async def rows_page(db, query, model, cursor, limit, date="created_at"):
    column = getattr(model, date)
    return list(
        await db.scalars(
            before(query, column, model.id, cursor)
            .order_by(column.desc(), model.id.desc())
            .limit(limit + 1)
        )
    )


def fields(row, *names):
    return {name: getattr(row, name) for name in names}


def user_state(user):
    return {
        **fields(user, "status", "daily_ai_quota", "is_admin", "failed_login_count"),
        "locked_until": user.locked_until.isoformat() if user.locked_until else None,
    }


def run_out(row):
    return {
        **fields(
            row,
            "id",
            "user_id",
            "profile_id",
            "kind",
            "model",
            "status",
            "input_tokens",
            "output_tokens",
            "created_at",
            "finished_at",
            "cancel_requested",
        ),
        "duration_seconds": round(
            ((row.finished_at or utcnow()) - row.created_at).total_seconds(), 2
        ),
        "error": "任务未完成，请检查配置或联系用户重新提交" if row.error else None,
    }


@router.get("/session")
async def session(db: DB, current: CurrentSessionDep):
    _, session = await admin_identity(db, current)
    return {
        "expires_at": session.admin_until,
        "unlocked": bool(session.admin_until and session.admin_until > utcnow()),
    }


@router.post("/unlock")
async def unlock_session(
    body: Unlock, request: Request, db: DB, current: CurrentSessionDep, settings: AppSettings
):
    return await unlock(db, current, body.password, settings, request)


@router.post("/lock")
async def lock_session(request: Request, db: DB, current: CurrentSessionDep):
    user, session = await admin_identity(db, current, lock=True)
    session.admin_until = None
    audit(db, request, user.id, "lock", user.id, "主动锁定后台")
    await db.commit()
    return {"locked": True}


@router.get("/overview")
async def overview(db: DB, admin: Admin, days: int = Query(7, ge=7, le=30)):
    if days not in (7, 30):
        raise HTTPException(422, "请选择7天或30天")
    today = utcnow().astimezone(ZoneInfo("Asia/Shanghai")).date()
    start = datetime.combine(
        today - timedelta(days=days - 1), datetime.min.time(), ZoneInfo("Asia/Shanghai")
    )
    totals = {
        "users": await db.scalar(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        ),
        "profiles": await db.scalar(
            select(func.count()).select_from(Profile).where(Profile.deleted_at.is_(None))
        ),
        "calculations": await db.scalar(
            select(func.count())
            .select_from(CalculationRun)
            .where(CalculationRun.created_at >= start)
        ),
    }
    status_rows = (
        await db.execute(
            select(AIRun.status, func.count())
            .where(AIRun.created_at >= start)
            .group_by(AIRun.status)
        )
    ).all()
    counts = dict(status_rows)
    totals.update(
        {key: counts.get(key, 0) for key in ["succeeded", "failed", "running", "cancelled"]}
    )
    denominator = totals["succeeded"] + totals["failed"]
    totals["success_rate"] = totals["succeeded"] / denominator if denominator else None
    tokens = (
        await db.execute(
            select(
                func.coalesce(func.sum(AIRun.input_tokens), 0),
                func.coalesce(func.sum(AIRun.output_tokens), 0),
            ).where(AIRun.created_at >= start)
        )
    ).one()
    totals["input_tokens"], totals["output_tokens"] = tokens
    day = func.date(func.timezone("Asia/Shanghai", AIRun.created_at))
    trend = (
        (
            await db.execute(
                select(
                    day.label("date"),
                    func.count().label("runs"),
                    func.sum(AIRun.input_tokens + AIRun.output_tokens).label("tokens"),
                    func.count().filter(AIRun.status == "failed").label("failed"),
                )
                .where(AIRun.created_at >= start)
                .group_by(day)
            )
        )
        .mappings()
        .all()
    )
    by_day = {str(row["date"]): dict(row) for row in trend}
    public = (
        (
            await db.execute(
                select(
                    func.count().label("runs"),
                    func.coalesce(
                        func.sum(HotCollectionRun.input_tokens + HotCollectionRun.output_tokens), 0
                    ).label("llm_tokens"),
                    func.coalesce(func.sum(HotCollectionRun.embedding_tokens), 0).label(
                        "embedding_tokens"
                    ),
                ).where(HotCollectionRun.created_at >= start)
            )
        )
        .mappings()
        .one()
    )
    return {
        "totals": totals,
        "days": days,
        "timezone": "Asia/Shanghai",
        "public_hotspots": dict(public),
        "trend": [
            by_day.get(
                str(today - timedelta(days=i)),
                {"date": str(today - timedelta(days=i)), "runs": 0, "tokens": 0, "failed": 0},
            )
            for i in reversed(range(days))
        ],
    }


@router.get("/users")
async def users(
    db: DB,
    admin: Admin,
    settings: AppSettings,
    q: str = Query("", max_length=120),
    status: Literal["active", "disabled"] | None = None,
    verified: bool | None = None,
    cursor: str | None = None,
    limit: int = Limit,
):
    query = select(User).where(User.deleted_at.is_(None))
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(User.email.ilike(pattern) | User.nickname.ilike(pattern))
    if status:
        query = query.where(User.status == status)
    if verified is not None:
        query = query.where(
            User.email_verified_at.is_not(None) if verified else User.email_verified_at.is_(None)
        )
    rows = await rows_page(db, query, User, cursor, limit)
    usage = {
        u.user_id: u
        for u in await db.scalars(
            select(ResourceUsage).where(ResourceUsage.user_id.in_([r.id for r in rows]))
        )
    }
    today = (
        utcnow()
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    daily_runs = dict(
        (
            await db.execute(
                select(AIRun.user_id, func.count())
                .where(AIRun.user_id.in_([r.id for r in rows]), AIRun.created_at >= today)
                .group_by(AIRun.user_id)
            )
        ).all()
    )
    return page(
        rows,
        limit,
        lambda u: {
            **fields(u, "id", "email", "nickname", "created_at", "last_login_at"),
            **user_state(u),
            "verified": u.email_verified_at is not None,
            "today_ai_runs": daily_runs.get(u.id, 0),
            "daily_ai_limit": u.daily_ai_quota
            if u.daily_ai_quota is not None
            else settings.ai_daily_quota,
            "storage_bytes": usage[u.id].storage_bytes if u.id in usage else 0,
            "profile_count": usage[u.id].profile_count if u.id in usage else 0,
            "storage_limit": (100 if u.email_verified_at else 10) * 1024 * 1024,
        },
    )


@router.post("/users/{user_id}/actions")
async def user_action(user_id: UUID, body: UserAction, request: Request, db: DB, admin: Admin):
    target = await db.scalar(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise HTTPException(404, "找不到用户")
    old = user_state(target)
    if body.expected != old:
        raise HTTPException(409, "账号状态已变化，请刷新后重新确认")
    if body.action == "disable":
        if user_id == admin.id:
            raise HTTPException(409, "不能停用当前管理员")
        if target.is_admin:
            count = await db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.is_admin.is_(True),
                    User.status == "active",
                    User.email_verified_at.is_not(None),
                    User.deleted_at.is_(None),
                )
            )
            if count <= 1:
                raise HTTPException(409, "必须保留一个可用管理员")
        target.status = "disabled"
        await db.execute(
            update(AIRun)
            .where(AIRun.user_id == user_id, AIRun.status == "running")
            .values(
                cancel_requested=True,
                status="cancelled",
                finished_at=utcnow(),
                error="账号停用，任务已取消",
            )
        )
    elif body.action == "enable":
        target.status = "active"
    elif body.action == "unlock":
        target.failed_login_count, target.locked_until = 0, None
    elif body.action == "quota":
        target.daily_ai_quota = body.quota
    if body.action in ("disable", "revoke_sessions"):
        await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    audit(
        db,
        request,
        admin.id,
        "user." + body.action,
        target.id,
        body.reason,
        {"before": old, "after": user_state(target)},
    )
    await db.commit()
    return {"state": user_state(target)}


@router.get("/runs")
async def runs(
    db: DB,
    admin: Admin,
    user_id: UUID | None = None,
    model: str = Query("", max_length=100),
    kind: Literal["interview", "content", "report"] | None = None,
    status: Literal["running", "succeeded", "failed", "cancelled"] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Limit,
):
    query = select(AIRun).options(defer(AIRun.input), defer(AIRun.output))
    for column, value in [
        (AIRun.user_id, user_id),
        (AIRun.model, model or None),
        (AIRun.kind, kind),
        (AIRun.status, status),
    ]:
        if value is not None:
            query = query.where(column == value)
    if since:
        query = query.where(AIRun.created_at >= since)
    if until:
        query = query.where(AIRun.created_at < until)
    rows = await rows_page(db, query, AIRun, cursor, limit)
    return page(rows, limit, run_out)


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: UUID, body: Reason, request: Request, db: DB, admin: Admin):
    row = await db.scalar(select(AIRun).where(AIRun.id == run_id).with_for_update())
    if row is None:
        raise HTTPException(404, "找不到任务")
    old = row.status
    if old == "running":
        row.status, row.cancel_requested, row.finished_at = "cancelled", True, utcnow()
    audit(
        db,
        request,
        admin.id,
        "run.cancel",
        run_id,
        body.reason,
        {"before": old, "after": row.status},
    )
    await db.commit()
    return run_out(row)


@router.get("/profiles")
async def profiles(
    db: DB, admin: Admin, user_id: UUID | None = None, cursor: str | None = None, limit: int = Limit
):
    query = select(Profile).options(
        load_only(
            Profile.id,
            Profile.user_id,
            Profile.name,
            Profile.template_key,
            Profile.industry,
            Profile.stage,
            Profile.revision,
            Profile.status,
            Profile.created_at,
            Profile.updated_at,
            Profile.deleted_at,
        )
    )
    if user_id:
        query = query.where(Profile.user_id == user_id)
    rows = await rows_page(db, query, Profile, cursor, limit)
    return page(
        rows,
        limit,
        lambda p: fields(
            p,
            "id",
            "user_id",
            "name",
            "template_key",
            "industry",
            "stage",
            "revision",
            "status",
            "created_at",
            "updated_at",
            "deleted_at",
        ),
    )


@router.post("/profiles/{profile_id}/inspect")
async def inspect(profile_id: UUID, body: Inspect, request: Request, db: DB, admin: Admin):
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(404, "找不到档案")
    if body.section == "parameters":
        result = fields(
            profile,
            "parameters",
            "value_proposition",
            "brand_voice",
            "city",
            "district",
            "stage",
            "revision",
        )
    else:
        model = {
            "history": ParameterChange,
            "evaluations": Evaluation,
            "chat": Message,
            "reports": EvaluationReport,
            "copy": ContentDraft,
        }[body.section]
        query = select(model)
        if model == Message:
            query = query.join(Conversation, Message.conversation_id == Conversation.id).where(
                Conversation.profile_id == profile_id,
                Message.payload["role"].astext.in_(["user", "assistant"]),
                Message.payload["content"].astext.is_not(None),
                Message.payload["tool_calls"].astext.is_(None),
            )
        elif model == EvaluationReport:
            query = query.join(Evaluation, EvaluationReport.evaluation_id == Evaluation.id).where(
                Evaluation.profile_id == profile_id
            )
        else:
            query = query.where(model.profile_id == profile_id)

        def serialize(row):
            if model == Message:
                return {
                    "id": row.id,
                    "role": row.payload["role"],
                    "content": row.payload.get("content"),
                    "created_at": row.created_at,
                }
            names = {
                ParameterChange: (
                    "id",
                    "profile_revision",
                    "parameter_key",
                    "old_value",
                    "new_value",
                    "source",
                    "reason",
                    "created_at",
                ),
                Evaluation: (
                    "id",
                    "profile_revision",
                    "label",
                    "parameters",
                    "results",
                    "summary",
                    "created_at",
                ),
                EvaluationReport: ("id", "status", "content", "created_at"),
                ContentDraft: ("id", "platform", "topic", "content", "status", "created_at"),
            }
            return fields(row, *names[model])

        result = page(
            await rows_page(db, query, model, body.cursor, body.limit), body.limit, serialize
        )
    audit(db, request, admin.id, "profile.read." + body.section, profile_id, body.reason)
    await db.commit()
    return result


@router.get("/hotspots")
async def hotspots(db: DB, admin: Admin, cursor: str | None = None, limit: int = Limit):
    rows = await rows_page(db, select(HotTopic), HotTopic, cursor, limit, "fetched_at")
    return page(
        rows,
        limit,
        lambda h: {
            **fields(
                h, "id", "title", "url", "channel", "safe", "manually_hidden", "fetched_at", "rank"
            ),
            "expired": h.fetched_at < utcnow() - timedelta(hours=24),
        },
        "fetched_at",
    )


@router.get("/collections")
async def collections(db: DB, admin: Admin, cursor: str | None = None, limit: int = Limit):
    rows = await rows_page(db, select(HotCollectionRun), HotCollectionRun, cursor, limit)
    return page(
        rows,
        limit,
        lambda row: {
            **fields(
                row,
                "id",
                "status",
                "model",
                "embedding_model",
                "input_tokens",
                "output_tokens",
                "embedding_tokens",
                "llm_calls",
                "embedding_calls",
                "created_at",
                "finished_at",
            ),
            "error": collection_error(row),
            "diagnostics": public_diagnostics(row.diagnostics),
        },
    )


@router.post("/hotspots/{topic_id}/visibility")
async def visibility(topic_id: UUID, body: Hide, request: Request, db: DB, admin: Admin):
    row = await db.scalar(select(HotTopic).where(HotTopic.id == topic_id).with_for_update())
    if row is None:
        raise HTTPException(404, "找不到来源")
    if row.manually_hidden != body.expected:
        raise HTTPException(409, "来源状态已变化，请刷新")
    old, row.manually_hidden = row.manually_hidden, body.hidden
    audit(
        db,
        request,
        admin.id,
        "hotspot.visibility",
        topic_id,
        body.reason,
        {"before": old, "after": body.hidden},
    )
    await db.commit()
    return {"hidden": row.manually_hidden}


@router.get("/audits")
async def audits(
    db: DB,
    admin: Admin,
    action: str = Query("", max_length=100),
    actor_id: UUID | None = None,
    target: str = Query("", max_length=100),
    result: Literal["success", "failed"] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Limit,
):
    query = select(AdminAudit)
    for column, value in [
        (AdminAudit.action, action or None),
        (AdminAudit.actor_id, actor_id),
        (AdminAudit.target, target or None),
        (AdminAudit.result, result),
    ]:
        if value is not None:
            query = query.where(column == value)
    if since:
        query = query.where(AdminAudit.created_at >= since)
    if until:
        query = query.where(AdminAudit.created_at < until)
    rows = await rows_page(db, query, AdminAudit, cursor, limit)
    return page(
        rows,
        limit,
        lambda a: fields(
            a,
            "id",
            "actor_id",
            "action",
            "target",
            "reason",
            "ip",
            "result",
            "changes",
            "created_at",
        ),
    )


@router.get("/system")
async def system(request: Request, db: DB, admin: Admin, settings: AppSettings):
    await db.execute(select(1))
    heartbeat = await db.get(WorkerHeartbeat, "main")
    last = await db.scalar(
        select(HotCollectionRun).order_by(HotCollectionRun.created_at.desc()).limit(1)
    )
    return {
        "database": "ok",
        "version": request.app.version,
        "models": {
            "interview": settings.interview_model,
            "report": settings.report_model,
            "embedding": settings.embedding_model,
        },
        "configured": {
            "ai": bool(settings.deepseek_api_key.get_secret_value()),
            "embedding": bool(settings.dashscope_api_key.get_secret_value()),
            "mail": settings.mail_backend == "smtp"
            and bool(settings.smtp_password.get_secret_value()),
        },
        "worker": {
            "last_seen": heartbeat.seen_at if heartbeat else None,
            "stale": not heartbeat or (utcnow() - heartbeat.seen_at).total_seconds() > 180,
        },
        "last_collection": fields(
            last, "status", "created_at", "finished_at", "llm_calls", "embedding_calls"
        )
        if last
        else None,
        "default_daily_ai_quota": settings.ai_daily_quota,
        "public_hot_daily_limit": settings.hot_daily_limit,
    }
