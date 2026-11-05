from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from app.auth.dependencies import CurrentUser, VerifiedUser
from app.db.base import utcnow
from app.db.models import AIRun, ContentDraft
from app.deps import DB, AppSettings
from app.llm.runs import reserve
from app.profiles import service as profiles
from app.profiles.schemas import StrictBody

from . import service
from .hot import recommendations

router = APIRouter(prefix="/api/profiles/{profile_id}/content", tags=["内容创作"])


class Generate(StrictBody):
    request_id: UUID
    topic_id: str = Field(max_length=80)
    platform: Literal["moments", "xiaohongshu"]
    confirmed_facts: str = Field(default="", max_length=2000)
    audience: Literal["buyers", "consumers"] | None = None
    voice: Literal["warm", "simple", "playful"] = "warm"


def out(item):
    return {
        "id": str(item.id),
        "platform": item.platform,
        "topic": item.topic,
        "angle": item.angle,
        "sources": item.sources,
        "content": item.content,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
    }


@router.get("/topics")
async def topics(profile_id: UUID, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    return service.topics(profile, today) + (
        await recommendations(db) if profile.template_key != "orchard" else []
    )


@router.get("/drafts")
async def drafts(profile_id: UUID, db: DB, user: CurrentUser):
    await profiles.get_owned_profile(db, user.id, profile_id)
    items = list(
        await db.scalars(
            select(ContentDraft)
            .where(ContentDraft.profile_id == profile_id)
            .order_by(ContentDraft.created_at.desc())
            .limit(50)
        )
    )
    for item in items:
        if item.status == "running":
            run = await db.get(AIRun, item.run_id)
            if run.status != "running" or run.lease_until < utcnow():
                item.status = "failed"
    await db.commit()
    return [out(item) for item in items]


@router.post("/drafts")
async def generate(
    profile_id: UUID,
    body: Generate,
    request: Request,
    db: DB,
    user: VerifiedUser,
    settings: AppSettings,
):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    choices = service.topics(profile, datetime.now(ZoneInfo("Asia/Shanghai")).date())
    if profile.template_key != "orchard":
        choices += await recommendations(db)
    topic = next((t for t in choices if t["id"] == body.topic_id), None)
    if topic is None:
        raise HTTPException(422, "这个选题已过期，请刷新后选择")
    # 由服务器选定来源，不接受模型或客户端伪造来源链接。
    data = {
        **body.model_dump(mode="json", exclude={"request_id"}),
        "prompt_version": service.PROMPT_VERSION,
        "topic": topic,
        "store": {
            "name": profile.name,
            "city": profile.city,
            "value_proposition": profile.value_proposition,
        },
    }
    if profile.template_key == "orchard":
        from app.templates.registry import parse_parameters

        orchard = parse_parameters("orchard", profile.parameters).orchard
        data["template_key"] = "orchard"
        data["audience"] = body.audience or (
            "buyers" if orchard.audience and orchard.audience.base == "wholesale" else "consumers"
        )
        data["store"] = {
            "name": profile.name,
            "city": profile.city,
            "supply": orchard.supply.base.model_dump(exclude_none=True) if orchard.supply else {},
            "varieties": [v.name for v in orchard.varieties.base] if orchard.varieties else [],
        }
    run, created = await reserve(db, user, profile_id, body.request_id, "content", data, settings)
    if not created:
        item = await db.scalar(select(ContentDraft).where(ContentDraft.run_id == run.id))
        if item is None:
            raise HTTPException(409, "草稿请求已中断，请重新生成")
        return out(item)
    draft = ContentDraft(
        profile_id=profile_id,
        run_id=run.id,
        platform=body.platform,
        topic=topic["title"],
        angle=topic["angle"],
        sources=topic["sources"]
        + (
            [
                {
                    "title": "用户确认的果园供货资料",
                    "url": None,
                    "excerpt": "；".join(
                        f"{label}：{data['store']['supply'][key]}"
                        for key, label in {
                            "specification": "规格",
                            "pack_net_kg": "每箱净重kg",
                            "supply_dates": "供货期",
                            "available_quantity": "供货量",
                            "minimum_order": "起订量",
                            "shipping_areas": "发货地区",
                            "verified_attributes": "已核实特点及依据",
                        }.items()
                        if key in data["store"]["supply"]
                    )
                    or "尚未填写对外供货资料",
                    "retrieved_at": utcnow().date().isoformat(),
                }
            ]
            if profile.template_key == "orchard"
            else []
        )
        + (
            [
                {
                    "title": "用户确认的门店事实",
                    "url": None,
                    "excerpt": body.confirmed_facts,
                    "retrieved_at": utcnow().date().isoformat(),
                }
            ]
            if body.confirmed_facts
            else []
        ),
        status="running",
    )
    db.add(draft)
    await db.commit()
    request.app.state.ai_hub.start(run.id, service.generate(request.app, run.id, draft.id))
    return out(draft)
