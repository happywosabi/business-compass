"""访谈工具只复用已有的档案与计算服务。工具协议是模型输入，不享有额外权限。"""

from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field

from app.engine import PhysicalStoreParams, estimate_traffic, evaluate
from app.evaluations import service as evaluations
from app.profiles import service as profiles
from app.profiles.schemas import ProfileUpdate, StrictBody
from app.templates import load_template


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


TOOLS = {
    "update_parameters": (
        UpdateParameters,
        "记录参数。键名与完整三档结构见参数清单；来源仅 user 或 ai_inferred。",
    ),
    "update_profile_info": (ProfileInfo, "更新基本信息，城市、名称、阶段或价值主张。"),
    "use_default": (Defaults, "用户同意后给指定参数补默认值，保留来源与依据。"),
    "estimate_traffic": (Traffic, "调用客流估算，保存原始输入但不填写日单量。"),
    "what_if": (WhatIf, "临时试算，不保存；参数未齐时返回缺项。"),
    "run_evaluation": (Empty, "用户确认后生成不可变测算快照。"),
    "show_quick_replies": (QuickReplies, "显示2–4个短选项，每个最多10字。"),
}


def definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": schema.model_json_schema(),
            },
        }
        for name, (schema, desc) in TOOLS.items()
    ]


def template_prompt():
    """展开每个值的实际约束，省去重复的 ParamValue 泛型定义，降低每轮输入量。"""
    metadata = profiles.template_info()

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
    template = load_template(profile.template_key)
    params = PhysicalStoreParams.model_validate(profile.parameters)
    order = {
        stage: i for i, stage in enumerate(["basic", "product", "shop", "costs", "traffic", "none"])
    }
    pending = sorted(
        [s for s in template.specs.values() if s.ask and params.get(s.key) is None],
        key=lambda s: order[s.stage],
    )
    return {
        "profile": profiles.profile_out(profile).model_dump(mode="json"),
        "next_questions": [p.model_dump() for p in pending[:3]],
        "quick_missing": template.quick_missing(params),
        "can_evaluate": not template.quick_missing(params),
        "evaluation_instruction": "关键项齐全，用户确认测算就直接调用 run_evaluation，其余计算缺项由服务补默认值；面积和座位不影响运行。"
        if not template.quick_missing(params)
        else "请先补 quick_missing 中的关键参数，面积和座位不是必填。",
        "defaultable_keys": [
            key
            for key in params.missing_keys()
            if key in template.industry(profile.industry).params
            or key in template.industry(profile.industry).derived
            or key == "revenue.opening_month"
        ],
    }


async def execute(db, profile, name, arguments, revision, message_id: UUID):
    if name not in TOOLS:
        raise ValueError("未知工具")
    body = TOOLS[name][0].model_validate(arguments)
    if profile.revision != revision:
        raise HTTPException(409, "档案已在其他页面更新，请确认后继续")
    template = load_template(profile.template_key)
    extra = {}
    if name == "update_parameters":
        changes = {}
        for key, value in body.changes.items():
            if not isinstance(value, dict) or "base" not in value:
                value = {"base": value, "source": "user"}
            if value.get("source", "user") not in {"user", "ai_inferred"}:
                raise ValueError("AI 只能记录 user 或 ai_inferred，默认值请使用 use_default")
            if value.get("source") == "ai_inferred" and not value.get("note"):
                raise ValueError("AI 估算必须写明 note 依据")
            changes[key] = value
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
    elif name == "update_profile_info":
        info = ProfileUpdate(revision=revision, **body.model_dump(exclude_none=True))
        profile = await profiles.write_profile(
            db, profile, revision, info.model_dump(exclude={"revision"}, exclude_unset=True)
        )
    elif name == "use_default":
        # 默认值服务使用独立 commit 开关，工具结果会与写入同一事务提交。
        profile = await profiles.use_defaults(
            db, profile, revision, body.keys, commit=False, message_id=message_id
        )
    elif name == "estimate_traffic":
        result = estimate_traffic(
            body.method, body.inputs, template.traffic_defaults(profile.industry)
        )
        params = PhysicalStoreParams.model_validate(profile.parameters)
        records = dict(params.traffic_estimates or {})
        records[body.method] = {"inputs": body.inputs, "result": result.model_dump()}
        params.traffic_estimates = records
        profile = await profiles.write_profile(
            db, profile, revision, {"parameters": params.model_dump(mode="json")}
        )
        extra["traffic_estimate"] = result.model_dump()
    elif name == "run_evaluation":
        item = await evaluations.create_evaluation(
            db, profile, revision, trigger="interview", commit=False
        )
        extra = {
            "evaluation_id": str(item.id),
            "results": {
                **item.results,
                "scenarios": {
                    key: {k: v for k, v in value.items() if k != "monthly"}
                    for key, value in item.results["scenarios"].items()
                },
            },
            "summary": item.summary,
        }
    elif name == "what_if":
        result = await evaluations.try_changes(db, profile, body.changes, None, revision)
        extra["what_if"] = result.model_dump()
    elif name == "show_quick_replies":
        if any(len(s) > 10 for s in body.options):
            raise ValueError("快捷选项最多10字")
        extra["quick_replies"] = body.options
    params = PhysicalStoreParams.model_validate(profile.parameters)
    if not params.missing_keys():
        extra["checks"] = [
            c.model_dump() for c in evaluate(params, template.check_rules(profile.industry)).checks
        ]
    return profile, {**state(profile), **extra}
