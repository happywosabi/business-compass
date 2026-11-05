"""果园单位换算工具；上下文不完整则拒绝计算。"""

import re
from typing import Any, Literal

from pydantic import Field

from app.engine.orchard import OrchardParams
from app.profiles.schemas import StrictBody


class Convert(StrictBody):
    kind: Literal["weight", "price", "yield_per_mu", "labor"]
    amount: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal["kg", "jin", "tonne", "box", "day"]
    net_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    area_mu: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    days: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    people: int | None = Field(default=None, ge=1)


def convert(body: Convert) -> dict[str, Any]:
    factor = {"kg": 1, "jin": 0.5, "tonne": 1000}.get(body.unit)
    if body.unit == "box":
        if body.net_kg is None:
            raise ValueError("请先确认每箱水果净重，不能使用含包装毛重")
        factor = body.net_kg
    if body.kind == "labor":
        if body.unit != "day" or body.days is None or body.people is None:
            raise ValueError("日薪换算必须确认本期工作天数、领薪人数及每人日薪")
        result, unit = body.amount * body.days * body.people, "元/期"
    else:
        if factor is None:
            raise ValueError("重量单位应为斤、公斤、吨或已确认净重的箱")
        result = body.amount / factor if body.kind == "price" else body.amount * factor
        unit = "元/kg" if body.kind == "price" else "kg"
        if body.kind == "yield_per_mu":
            if body.area_mu is None:
                raise ValueError("亩产换总产量必须先确认该品种面积")
            result *= body.area_mu
    return {
        "kind": body.kind,
        "value": result,
        "unit": unit,
        "source": "user",
        "note": f"按已确认原始输入换算：{body.model_dump(exclude_none=True)}",
    }


PROMPT = """你是商业罗盘，帮助已投产果农建立果园经营档案。只核算明确起止日期的一个生产年/经营期总账，多个品种共用期间。先确认期间，再逐个品种采收量及采后损耗、客户类型、销售价格和成本、家庭劳动，最后请用户确认测算。每轮只问一个重要澄清，简短自然。用户已提供新数字时先记录能确定的内容；单位或上下文缺失则优先问该缺失，不要跳回无关的经营期问题。
audience记录主要对象：用户说主要批发则wholesale，即便同时零售；只有明确并重才mixed。主要批发不等于全批发；确认实际批发/零售比例，存在两个渠道不代表audience=mixed。默认统货单等级，可按用户信息展开分级，各等级占比和渠道占比各自合计100%。采收量不等于售出量，售出率针对扣损耗后可售量，未售出收入为零。全部缺失保持null，零必须经用户确认；不编造农业基准，不以设备购置充经营支出。
参数结构由定义提供。列表更新必须保留已有所有品种、等级、渠道ID和未修改数据；只新增项目生成新ID，不丢失其他品种。允许保存未齐的草稿。更正或撤回需更新/清空旧值，不把前后两次数值相加。
禁止为了占位或写备注调用update_parameters把已有参数清空；只有用户明确撤回/删除时才可清空。不完整的新信息先追问，不能破坏已记录内容。
所有斤/吨/箱价/亩产/日薪的换算必须先调用 convert_orchard_unit，用结果记参数并在note保留原话、原单位和换算依据；AI不得自行算术。每箱价格须问净重；亩产须问面积；日薪须确认本期工作天数和人数。月工资转本期须确认实际支付月数，不能默认全年或30天。只知道季节时问明确日期，不能擅自转成年产。资料不够先追问，不填写似是而非的数。
共同支出只记全园一次；已付工资在品种直接成本中，未付酬本人/亲属劳动估值单列，不能默认亲属免费，也不能重复扣。供货资料只存经确认的产品、包装、供货期、起订量、发货范围与特点；内部成本利润不用于营销。设备购置可选，未知不等于零。关键数据齐全后请用户确认 run_evaluation；不承诺回本、逐月现金流或投资收益。
"""


def guard_orchard_changes(changes: dict, user_text: str) -> None:
    """模型不能以占位之名清空列表或既有账目。"""
    if any(value is None for value in changes.values()) and not re.search(
        r"清空|删除|撤回|取消|去掉|不要.*(?:记|算)|不(?:记|算)|重置|清除", user_text
    ):
        raise ValueError(
            "未收到用户明确撤回要求，不得清空任何果园字段。信息不全请追问，保留原数据。"
        )


def guard_orchard_update(
    before: OrchardParams, after: OrchardParams, user_text: str, conversions: list[dict]
) -> None:
    """保留稳定ID，并核对非标准单位的写入确实来自代码换算。"""
    removal = re.search(
        r"清空|删除|撤回|取消|去掉|不要.*(?:记|算)|不(?:记|算)|重置|清除", user_text
    )

    def flatten(node, path=()):
        values = {}
        if isinstance(node, dict):
            if "base" in node and isinstance(node["base"], (float, int)):
                values[path] = node
            else:
                for key, value in node.items():
                    values.update(flatten(value, (*path, key)))
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    values.update(flatten(item, (*path, item.get("id", "unknown"))))
        return values

    def ids(params):
        result = set()
        for v in params.orchard.varieties.base if params.orchard.varieties else []:
            result.add((v.id,))
            for g in v.grades:
                result.add((v.id, g.id))
                for c in g.channels:
                    result.add((v.id, g.id, c.id))
        return result

    if not removal and ids(before) - ids(after):
        raise ValueError(
            "更新必须保留原有品种、等级及渠道的ID和数据；只修改用户更正的项目。删除须由用户明确提出。"
        )

    def validate_source(node):
        if isinstance(node, dict):
            if "base" in node and "source" in node:
                if node["source"] not in {"user", "ai_inferred"}:
                    raise ValueError("AI果园字段来源仅允许user或ai_inferred")
                if node["source"] == "ai_inferred" and not node.get("note"):
                    raise ValueError("AI估算须在note写明依据")
            for value in node.values():
                validate_source(value)
        elif isinstance(node, list):
            for value in node:
                validate_source(value)

    validate_source(after.model_dump())
    old, new = flatten(before.model_dump()), flatten(after.model_dump())
    if not removal and old.keys() - new.keys():
        raise ValueError("不得清空已记录数值；更新时保留原数据，明确撤回后才可删除。")
    weight_raw = re.search(
        r"吨|亩产|(?:采收|产量|收成|收获|总量|总产|重量).{0,20}斤|\d+(?:\.\d+)?\s*斤(?:.{0,5}(?:采收|产量|收成))",
        user_text,
    )
    price_raw = re.search(
        r"(?:每|一|/)(?:斤|箱)|元[／/](?:斤|箱)|(?:斤|箱).{0,8}\d+.{0,2}元", user_text
    )
    labor_raw = re.search(r"日薪|每天.{0,10}\d+|每日.{0,10}\d+", user_text)
    for path, value in new.items():
        if path in old and value["base"] == old[path]["base"]:
            continue
        field = path[-1]
        allowed_kinds = None
        if field == "harvest_kg" and weight_raw:
            allowed_kinds = {"weight", "yield_per_mu"}
        elif field == "price" and price_raw:
            allowed_kinds = {"price"}
        elif field in {"paid_labor", "unpaid_labor"} and labor_raw and value["base"] != 0:
            allowed_kinds = {"labor"}
        if allowed_kinds and not any(
            c.get("kind") in allowed_kinds and abs(c["value"] - value["base"]) < 1e-6
            for c in conversions
        ):
            raise ValueError(
                "非公斤、非元/kg或日薪输入必须先调用convert_orchard_unit，确认必要上下文后按返回值保存，不能自行换算。"
            )
        if allowed_kinds and not value.get("note"):
            raise ValueError("换算字段必须在note保留原话、原单位和换算依据。")
