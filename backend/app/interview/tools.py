"""访谈工具只复用已有的档案与计算服务。工具协议是模型输入，不享有额外权限。"""

import json
import re
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from app.confirmations import propose
from app.db.models import Message
from app.engine import estimate_traffic
from app.evaluations import service as evaluations
from app.profiles import service as profiles
from app.profiles.schemas import ProfileUpdate, StrictBody
from app.templates import load_template
from app.templates.registry import parse_parameters

from .amounts import daily_orders, guard_changes, monthly_amount
from .orchard import Convert, convert, guard_orchard_changes, guard_orchard_update


class UpdateParameters(StrictBody):
    changes: dict[str, Any] = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=1000)


class ProfileInfo(StrictBody):
    name: str | None = None
    city: str | None = None
    district: str | None = None
    stage: Literal["idea", "preparing", "operating"] | None = None
    value_proposition: dict[str, str] | None = None


class Defaults(StrictBody):
    keys: list[str] = Field(min_length=1, max_length=40)


class Traffic(StrictBody):
    method: Literal["location", "benchmark", "capacity"]
    inputs: dict[str, Any]


class WhatIf(StrictBody):
    changes: dict[str, Any] = Field(min_length=1, max_length=20)


class QuickReplies(StrictBody):
    options: list[str] = Field(min_length=2, max_length=4)


class Empty(StrictBody):
    pass


class PeriodicValue(StrictBody):
    key: Literal[
        "fixed_cost.rent",
        "fixed_cost.owner_salary",
        "fixed_cost.staff",
        "revenue.daily_orders",
        "fruit.sales_amount",
        "fruit.rent",
        "fruit.staff_cost",
        "fruit.owner_salary",
        "fruit.utilities",
        "fruit.delivery_fixed",
        "fruit.other_fixed",
    ]
    amount: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="用户原始金额（元）或订单数量，不是换算后的值；员工填写每人金额",
    )
    period: Literal["day", "month", "year"]
    days_per_month: float | None = Field(
        default=None,
        gt=0,
        le=31,
        description="用户明确给出或确认的工作/支付/营业天数；不确定就先追问，不能猜30",
    )
    staff_count: int | None = Field(
        default=None, ge=1, description="员工人数，不含单独记老板工资的本人；写staff时必填"
    )
    staff_role: str = Field(default="店员", min_length=1, max_length=60)
    reason: str = Field(min_length=1, max_length=1000)


TOOLS = {
    "update_parameters": (
        UpdateParameters,
        "记录参数。键名与完整三档结构见参数清单；来源仅 user 或 ai_inferred。撤回字段时将该键直接设为null，不要写base:null。",
    ),
    "update_profile_info": (ProfileInfo, "更新基本信息，城市、名称、阶段或价值主张。"),
    "record_periodic_value": (
        PeriodicValue,
        "记录带日/月/年单位的租金、老板工资、员工每人工资或单量，代码负责换算。日薪需先确认工作天数，月单量需确认营业天数。金额不能当单量。",
    ),
    "use_default": (Defaults, "提出补默认值确认卡片；只有用户点击按钮后才会写入。"),
    "estimate_traffic": (Traffic, "调用客流估算，保存原始输入但不填写日单量。"),
    "what_if": (WhatIf, "临时试算，不保存；参数未齐时返回缺项。"),
    "run_evaluation": (Empty, "提出正式测算确认卡片；只有用户点击按钮后才会执行。"),
    "show_quick_replies": (QuickReplies, "显示2–4个短选项，每个最多10字。"),
}


def definitions(key="physical_store", industry=None):
    available = dict(TOOLS)
    if industry == "fruit_retail":
        available = {
            k: v for k, v in available.items() if k not in {"estimate_traffic", "use_default"}
        }
    if key == "orchard":
        available = {
            k: v
            for k, v in available.items()
            if k not in {"record_periodic_value", "estimate_traffic", "use_default"}
        }
        available["convert_orchard_unit"] = (
            Convert,
            "换算原始斤/吨/箱价格/亩产/日薪，缺净重、面积、天数或人数时须追问。结果需另调用update_parameters保存。",
        )
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": schema.model_json_schema(),
            },
        }
        for name, (schema, desc) in available.items()
    ]


def template_prompt(key="physical_store", industry=None):
    """展开每个值的实际约束，省去重复的 ParamValue 泛型定义，降低每轮输入量。"""
    metadata = profiles.template_info(key, industry)

    def compact(schema):
        if "$ref" in schema:
            return compact(metadata.definitions[schema["$ref"].rsplit("/", 1)[-1]])
        return {
            key: (
                {k: compact(v) for k, v in value.items()}
                if key == "properties"
                else [compact(v) for v in value]
                if key == "anyOf"
                else compact(value)
                if key == "items"
                else value
            )
            for key, value in schema.items()
            if key
            in {
                "type",
                "properties",
                "items",
                "enum",
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "anyOf",
                "required",
            }
        }

    return [
        {
            "key": field.key,
            "label": field.label,
            "unit": field.unit,
            "ask": field.ask,
            "three_tier": field.three_tier,
            "value": compact(field.value_schema),
        }
        for field in metadata.fields
    ]


def state(profile):
    template = load_template(profile.template_key, profile.industry)
    params = parse_parameters(profile.template_key, profile.parameters)
    order = {
        stage: i for i, stage in enumerate(["basic", "product", "shop", "costs", "traffic", "none"])
    }
    pending = sorted(
        [
            s
            for s in template.specs.values()
            if s.ask
            and params.get(s.key) is None
            and (profile.industry != "fruit_retail" or s.key in params.missing_keys())
        ],
        key=lambda s: order[s.stage],
    )
    instruction = (
        "关键项齐全，用户确认后测算；缺项按当前口径逐项询问，水果店不提供行业默认值。"
        if profile.industry == "fruit_retail"
        else "关键项齐全，用户确认后测算；果园缺项须逐项确认，不补农业默认值。"
        if profile.template_key == "orchard"
        else "关键项齐全，用户确认测算就直接调用 run_evaluation，其余计算缺项由服务补默认值；面积和座位不影响运行。"
        if not template.quick_missing(params)
        else "请先补 quick_missing 中的关键参数，面积和座位不是必填。"
    )
    return {
        "profile": profiles.profile_out(profile).model_dump(mode="json"),
        "next_questions": [
            p.model_dump() for p in pending[: 2 if profile.industry == "fruit_retail" else 3]
        ],
        "quick_missing": template.quick_missing(params),
        "can_evaluate": not template.quick_missing(params),
        "evaluation_instruction": instruction,
        "defaultable_keys": [
            key
            for key in params.missing_keys()
            if key in template.industry(profile.industry).params
            or key in template.industry(profile.industry).derived
            or key == "revenue.opening_month"
        ],
    }


async def execute(
    db, profile, name, arguments, revision, message_id: UUID, *, user_text="", previous_reply=""
):
    if profile.industry == "fruit_retail" and name in {"estimate_traffic", "use_default"}:
        raise ValueError("水果店没有行业默认值或客流估算工具")
    if profile.template_key == "orchard" and name in {
        "record_periodic_value",
        "estimate_traffic",
        "use_default",
    }:
        raise ValueError("此工具不适用果园模板")
    if name == "convert_orchard_unit":
        if profile.template_key != "orchard":
            raise ValueError("仅适用果园")
        return profile, {**state(profile), "conversion": convert(Convert.model_validate(arguments))}
    if name not in TOOLS:
        raise ValueError("未知工具")
    body = TOOLS[name][0].model_validate(arguments)
    if profile.revision != revision:
        raise HTTPException(409, "档案已在其他页面更新，请确认后继续")
    template = load_template(profile.template_key, profile.industry)
    extra = {}
    if name == "update_parameters":
        normalized = {
            key: None if isinstance(value, dict) and value.get("base", "missing") is None else value
            for key, value in body.changes.items()
        }
        if profile.template_key == "orchard":
            guard_orchard_changes(normalized, user_text)
        elif profile.industry == "fruit_retail":
            guard_fruit(normalized, user_text, previous_reply)
        else:
            guard_changes(normalized, user_text, previous_reply)
        changes = {}
        for key, value in normalized.items():
            if value is None:
                changes[key] = None
                continue
            if not isinstance(value, dict) or "base" not in value:
                value = {"base": value, "source": "user"}
            if value.get("source", "user") not in {"user", "ai_inferred"}:
                raise ValueError("AI 只能记录 user 或 ai_inferred，默认值请使用 use_default")
            if value.get("source") == "ai_inferred" and not value.get("note"):
                raise ValueError("AI 估算必须写明 note 依据")
            changes[key] = value
        if profile.template_key == "orchard":
            current_message = await db.get(Message, message_id)
            conversions = []
            if current_message:
                rows = await db.scalars(
                    select(Message).where(Message.run_id == current_message.run_id)
                )
                for row in rows:
                    if row.payload.get("role") == "tool":
                        try:
                            conversion = json.loads(row.payload["content"]).get("conversion")
                            if conversion:
                                conversions.append(conversion)
                        except (ValueError, TypeError):
                            continue
            before = parse_parameters(profile.template_key, profile.parameters)
            guard_orchard_update(before, before.with_values(changes), user_text, conversions)
        profile = await profiles.edit_parameters(
            db,
            profile,
            revision,
            changes,
            source="ai_extraction",
            reason=body.reason,
            message_id=message_id,
            commit=False,
        )
    elif name == "record_periodic_value":
        if body.key.startswith("fruit.") != (profile.industry == "fruit_retail"):
            raise ValueError("周期工具参数与业态不匹配")
        if body.key == "fruit.sales_amount":
            guard_fruit({body.key: body.amount}, user_text, previous_reply, converting=True)
            if body.period == "year":
                raise ValueError("营业额仅支持日/月；年金额请先明确月口径")
            profile = await profiles.edit_parameters(
                db,
                profile,
                revision,
                {
                    "fruit.revenue_basis": {"base": "revenue"},
                    "fruit.sales_amount": {
                        "base": body.amount,
                        "note": f"原始营业额{body.amount:g}元/{body.period}",
                    },
                    "fruit.sales_period": {"base": body.period},
                    "fruit.daily_transactions": None,
                    "fruit.avg_ticket": None,
                },
                source="ai_extraction",
                reason=body.reason,
                message_id=message_id,
                commit=False,
            )
            return profile, state(profile)
        if body.key == "revenue.daily_orders":
            guard_changes({body.key: body.amount}, user_text, previous_reply, converting=True)
            value = daily_orders(body.amount, body.period, body.days_per_month)
        else:
            value = monthly_amount(body.amount, body.period, body.days_per_month)
        unit = "单" if body.key == "revenue.daily_orders" else "元"
        period_label = {"day": "天", "month": "月", "year": "年"}[body.period]
        note = f"用户原话：{body.amount:g}{unit}/{period_label}。"
        if body.days_per_month is not None:
            note += f"按用户确认每月{body.days_per_month:g}天换算。"
        if body.period == "year":
            note += "按每年12个月换算。"
        if body.key == "fruit.staff_cost":
            if body.staff_count is None:
                raise ValueError("请确认实际付薪人数及每人金额，老板工资单列")
            value *= body.staff_count
            note += f"实际付薪{body.staff_count}人。"
        if body.key == "fixed_cost.staff":
            if body.staff_count is None:
                raise ValueError(
                    "请确认除老板本人外的员工人数，亲属是否领工资需单独询问，不能默认免费劳动。"
                )
            value = [{"role": body.staff_role, "count": body.staff_count, "monthly_cost": value}]
        profile = await profiles.edit_parameters(
            db,
            profile,
            revision,
            {body.key: {"base": value, "source": "user", "note": note}},
            source="ai_extraction",
            reason=body.reason,
            message_id=message_id,
            commit=False,
        )
    elif name == "update_profile_info":
        info = ProfileUpdate(revision=revision, **body.model_dump(exclude_none=True))
        profile = await profiles.write_profile(
            db, profile, revision, info.model_dump(exclude={"revision"}, exclude_unset=True)
        )
    elif name == "use_default":
        extra["confirmation"] = await propose(db, profile, "defaults", {"keys": body.keys})
    elif name == "estimate_traffic":
        result = estimate_traffic(
            body.method, body.inputs, template.traffic_defaults(profile.industry)
        )
        params = parse_parameters(profile.template_key, profile.parameters)
        records = dict(params.traffic_estimates or {})
        records[body.method] = {"inputs": body.inputs, "result": result.model_dump()}
        params.traffic_estimates = records
        profile = await profiles.write_profile(
            db, profile, revision, {"parameters": params.model_dump(mode="json")}
        )
        extra["traffic_estimate"] = result.model_dump()
    elif name == "run_evaluation":
        extra["confirmation"] = await propose(db, profile, "evaluation")
    elif name == "what_if":
        result = await evaluations.try_changes(db, profile, body.changes, None, revision)
        extra["what_if"] = result.model_dump()
        extra["confirmation"] = await propose(db, profile, "apply", {"changes": body.changes})
    elif name == "show_quick_replies":
        if any(len(s) > 10 for s in body.options):
            raise ValueError("快捷选项最多10字")
        extra["quick_replies"] = body.options
    return profile, {**state(profile), **extra}


def guard_fruit(changes, user_text, previous_reply="", *, converting=False):
    revenue = {"fruit.sales_amount", "fruit.daily_transactions", "fruit.avg_ticket"}
    selected = revenue & {k for k, v in changes.items() if v is not None}
    explicit_revenue = bool(re.search(r"营业额|销售额|流水|客单|交易|笔", user_text))
    if (
        selected
        and not explicit_revenue
        and (
            re.search(r"工资|月薪|日薪|每人|两个人|[两二2]个人", user_text)
            or re.search(r"工资|月薪|日薪|每人", previous_reply)
        )
    ):
        raise ValueError("这笔数字可能是人工工资；请承接上一问确认，不能当营业额或交易笔数")
    if (
        "fruit.daily_transactions" in selected
        and re.search(r"元|营业额|销售额|流水", user_text)
        and not re.search(r"交易|笔", user_text)
    ):
        raise ValueError("金额不是交易笔数，请按原始营业额及日/月周期保存")
    if "fruit.avg_ticket" in selected and re.search(
        r"元[/／每]?(?:斤|kg|公斤)|每斤|一斤", user_text
    ):
        raise ValueError("水果按重量售价不等于每笔客单价，请保存公开零售价并追问整笔消费")
    if not converting and re.search(r"每天|每日|每月|日薪|月薪|/天|/月|每年|年租", user_text):
        periodic = {
            "fruit.sales_amount",
            "fruit.rent",
            "fruit.owner_salary",
            "fruit.staff_cost",
            "fruit.utilities",
            "fruit.delivery_fixed",
            "fruit.other_fixed",
        }
        if periodic & {k for k, v in changes.items() if v is not None}:
            raise ValueError("带周期金额请调用record_periodic_value，传原始金额，不自行换算")
    if (
        changes.get("fruit.gross_margin") is not None
        and re.search(r"加价|赚[三两二一四五六七八九十\d]成", user_text)
        and not re.search(r"毛利率|售价.*分母", user_text)
    ):
        raise ValueError("加价率不等于毛利率；请先确认以售价还是进价为分母")
