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
    hot_topic_id: str | None = Field(default=None, max_length=80)
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
    return service.topics(profile, today)


@router.get("/hot-topics")
async def hot_topics(profile_id: UUID, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    return await recommendations(db, profile.template_key, profile.industry)


@router.post("/hot-topics/refresh")
async def refresh_hot_topics(
    profile_id: UUID, request: Request, db: DB, user: VerifiedUser, settings: AppSettings
):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    return {
        "topics": await recommendations(db, profile.template_key, profile.industry),
        "error": None,
        "message": "已刷新已有来源。公共热点由后台定时采集，此操作不调用 AI、不消耗个人额度。",
    }


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
    # 重放按原请求判断，不因来源刷新、跨日或档案变化重复扣费。
    previous = await db.scalar(
        select(AIRun).where(AIRun.user_id == user.id, AIRun.request_id == body.request_id)
    )
    if previous:
        payload = body.model_dump(mode="json", exclude={"request_id"})
        if (
            previous.profile_id != profile_id
            or previous.kind != "content"
            or previous.input.get("request", {key: previous.input.get(key) for key in payload})
            != payload
        ):
            raise HTTPException(409, "同一个请求编号不能用于不同内容")
        item = await db.scalar(select(ContentDraft).where(ContentDraft.run_id == previous.id))
        if item is None:
            raise HTTPException(409, "草稿请求已中断，请重新生成")
        return out(item)
    choices = service.topics(profile, datetime.now(ZoneInfo("Asia/Shanghai")).date())
    topic = next((t for t in choices if t["id"] == body.topic_id), None)
    if topic is None:
        raise HTTPException(422, "这个选题已过期，请刷新后选择")
    hot = None
    if body.hot_topic_id:
        hot = next(
            (
                t
                for t in await recommendations(db, profile.template_key, profile.industry)
                if t["id"] == body.hot_topic_id
            ),
            None,
        )
        if hot is None:
            raise HTTPException(422, "这个热点已过期或不适合当前档案，请刷新后选择")
    # 由服务器选定来源，不接受模型或客户端伪造来源链接。
    data = {
        **body.model_dump(mode="json", exclude={"request_id"}),
        "request": body.model_dump(mode="json", exclude={"request_id"}),
        "prompt_version": service.PROMPT_VERSION,
        "topic": topic,
        "hot_topic": hot,
        "store": {
            "name": profile.name,
            "city": profile.city,
            "value_proposition": profile.value_proposition,
        },
    }
    if profile.industry == "fruit_retail":
        from app.templates.registry import parse_parameters

        fruit = parse_parameters(profile.template_key, profile.parameters).fruit
        data["industry"] = "fruit_retail"
        data["store"] = {
            "name": profile.name,
            "city": profile.city,
            "location": fruit.location.base if fruit.location else None,
            "channels": fruit.channels.base if fruit.channels else None,
            "public_facts": fruit.public_facts.base.model_dump(exclude_none=True)
            if fruit.public_facts
            else {},
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
        topic=topic["title"] + (f" · {hot['title']}" if hot else ""),
        angle=topic["angle"],
        sources=topic["sources"]
        + (
            [
                {
                    "title": "用户确认的水果零售公开资料",
                    "url": None,
                    "excerpt": "；".join(
                        f"{label}：{data['store']['public_facts'][key]}"
                        for key, label in {
                            "products": "在售水果",
                            "retail_prices": "零售价与单位",
                            "confirmed_origin": "已确认产地",
                            "delivery_rules": "配送规则",
                            "promotions": "活动与限制",
                        }.items()
                        if data["store"]["public_facts"].get(key)
                    )
                    or "尚未填写对外商品与活动资料",
                    "retrieved_at": utcnow().date().isoformat(),
                }
            ]
            if profile.industry == "fruit_retail"
            else []
        )
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
