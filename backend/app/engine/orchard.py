"""成熟果园单个经营期总账；纯计算，不读文件、不推断农业基准。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .params import (
    SCENARIOS,
    MissingParametersError,
    NonNegative,
    ParamValue,
    Rate,
    Scenario,
    Source,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Amount(ParamValue[NonNegative]):
    pass


class Period(Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self) -> Period:
        if self.end < self.start:
            raise ValueError("结束日期不能早于开始日期")
        return self


class OrchardChannel(Strict):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["wholesale", "retail"]
    share: Rate
    price: Amount | None = None
    packaging_per_kg: Amount | None = None
    logistics_per_kg: Amount | None = None
    fee_rate: ParamValue[Rate] | None = None


class Grade(Strict):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(default="统货", min_length=1, max_length=80)
    share: Rate = 1
    sell_through: ParamValue[Rate] | None = None
    channels: list[OrchardChannel] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def shares(self) -> Grade:
        if self.channels and abs(sum(c.share for c in self.channels) - 1) > 1e-6:
            raise ValueError("渠道占比之和必须为100%")
        if len({c.kind for c in self.channels}) != len(self.channels):
            raise ValueError("每个等级批发和零售渠道各限一个")
        if len({c.id for c in self.channels}) != len(self.channels):
            raise ValueError("渠道ID不能重复")
        return self


class DirectCosts(Strict):
    inputs: Amount | None = None
    irrigation: Amount | None = None
    paid_labor: Amount | None = None
    other: Amount | None = None


class Variety(Strict):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    area_mu: float | None = Field(default=None, gt=0)
    harvest_start: date | None = None
    harvest_end: date | None = None
    harvest_kg: Amount | None = None
    loss_rate: ParamValue[Rate] | None = None
    grades: list[Grade] = Field(default_factory=list, max_length=20)
    costs: DirectCosts = Field(default_factory=DirectCosts)

    @model_validator(mode="after")
    def shares(self) -> Variety:
        if self.grades and abs(sum(g.share for g in self.grades) - 1) > 1e-6:
            raise ValueError("等级占比之和必须为100%")
        if len({g.id for g in self.grades}) != len(self.grades):
            raise ValueError("等级ID不能重复")
        if self.harvest_start and self.harvest_end and self.harvest_end < self.harvest_start:
            raise ValueError("采收结束日期不能早于开始日期")
        return self


class SharedCosts(Strict):
    land_rent: Amount | None = None
    maintenance: Amount | None = None
    other: Amount | None = None


class Supply(Strict):
    specification: str | None = Field(default=None, max_length=300)
    pack_net_kg: float | None = Field(default=None, gt=0)
    supply_dates: str | None = Field(default=None, max_length=200)
    available_quantity: str | None = Field(default=None, max_length=200)
    minimum_order: str | None = Field(default=None, max_length=200)
    shipping_areas: str | None = Field(default=None, max_length=300)
    verified_attributes: str | None = Field(default=None, max_length=1000)


class OrchardSection(Strict):
    period: ParamValue[Period] | None = None
    audience: ParamValue[Literal["wholesale", "retail", "mixed"]] | None = None
    varieties: ParamValue[list[Variety]] | None = None
    shared_costs: ParamValue[SharedCosts] | None = None
    unpaid_labor: Amount | None = None
    equipment: Amount | None = None
    supply: ParamValue[Supply] | None = None


ORCHARD_KEYS = tuple(f"orchard.{k}" for k in OrchardSection.model_fields)
MAX_ORCHARD_CHANNELS = 200
MAX_SENSITIVITY_RANGES = 100
REQUIRED = (
    "orchard.period",
    "orchard.audience",
    "orchard.varieties",
    "orchard.shared_costs",
    "orchard.unpaid_labor",
)


def _complete_varieties(value: ParamValue[list[Variety]] | None) -> bool:
    if not value or not value.base:
        return False
    for v in value.base:
        if v.harvest_kg is None or v.loss_rate is None or not v.grades:
            return False
        if any(getattr(v.costs, k) is None for k in DirectCosts.model_fields):
            return False
        for g in v.grades:
            if g.sell_through is None or not g.channels:
                return False
            if any(
                any(
                    getattr(c, k) is None
                    for k in ("price", "packaging_per_kg", "logistics_per_kg", "fee_rate")
                )
                for c in g.channels
            ):
                return False
    return True


class OrchardParams(Strict):
    schema_version: Literal[2] = 2
    orchard: OrchardSection = Field(default_factory=OrchardSection)

    @model_validator(mode="after")
    def validate_entries(self) -> OrchardParams:
        varieties = self.orchard.varieties
        if varieties:
            if varieties.pessimistic is not None or varieties.optimistic is not None:
                raise ValueError(
                    "情景请填写产量、售价、售出率或成本的三档值；等级和渠道占比保持不变"
                )
            if len(varieties.base) > 50:
                raise ValueError("品种最多50个")
            if len({v.id for v in varieties.base}) != len(varieties.base):
                raise ValueError("品种ID不能重复")
        for key in ORCHARD_KEYS:
            value = self.get(key)
            if (
                value
                and not isinstance(value.base, (int, float))
                and (value.pessimistic is not None or value.optimistic is not None)
            ):
                raise ValueError("仅数值支持三档范围")

        def check(value: ParamValue | None, high_good: bool) -> None:
            if value is None:
                return
            for s in ("pessimistic", "optimistic"):
                n = getattr(value, s)
                if n is not None and (
                    (n > value.base) if high_good == (s == "pessimistic") else (n < value.base)
                ):
                    raise ValueError("三档方向有误：产量、售价、售出率悲观较低；损耗和成本悲观较高")

        for v in varieties.base if varieties else []:
            check(v.harvest_kg, True)
            check(v.loss_rate, False)
            for k in DirectCosts.model_fields:
                check(getattr(v.costs, k), False)
            for g in v.grades:
                check(g.sell_through, True)
                for c in g.channels:
                    check(c.price, True)
                    for k in ("packaging_per_kg", "logistics_per_kg", "fee_rate"):
                        check(getattr(c, k), False)
        if self.orchard.shared_costs:
            for k in SharedCosts.model_fields:
                check(getattr(self.orchard.shared_costs.base, k), False)
        check(self.orchard.unpaid_labor, False)
        check(self.orchard.equipment, False)
        channels = (
            sum(len(g.channels) for v in varieties.base for g in v.grades) if varieties else 0
        )
        if channels > MAX_ORCHARD_CHANNELS:
            raise ValueError(
                f"单份果园档案最多{MAX_ORCHARD_CHANNELS}个销售渠道条目，请拆分经营方案"
            )
        if sum(1 for _ in _ranges(self)) > MAX_SENSITIVITY_RANGES:
            raise ValueError(f"三档范围最多{MAX_SENSITIVITY_RANGES}个，请保留关键假设的范围")
        return self

    def get(self, key: str) -> ParamValue[Any] | None:
        if key not in ORCHARD_KEYS:
            raise KeyError(f"未知果园参数：{key}")
        return getattr(self.orchard, key.split(".")[1])

    def with_values(self, changes: Mapping[str, Any]) -> OrchardParams:
        data = self.model_dump(mode="json")
        for key, value in changes.items():
            self.get(key)
            if isinstance(value, ParamValue):
                value = value.model_dump(mode="json")
            elif value is not None and not (isinstance(value, dict) and "base" in value):
                value = {"base": value}
            data["orchard"][key.split(".")[1]] = value
        return OrchardParams.model_validate(data)

    def missing_keys(self) -> list[str]:
        missing = [k for k in REQUIRED if self.get(k) is None]
        if "orchard.varieties" not in missing and not _complete_varieties(self.orchard.varieties):
            missing.append("orchard.varieties")
        shared = self.orchard.shared_costs
        if shared and any(getattr(shared.base, k) is None for k in SharedCosts.model_fields):
            missing.append("orchard.shared_costs")
        return missing

    def keys_by_source(self, source: Source) -> list[str]:
        return [k for k in ORCHARD_KEYS if self.get(k) and self.get(k).source == source]


class VarietyResult(Strict):
    id: str
    name: str
    harvest_kg: float
    saleable_kg: float
    sold_kg: float
    unsold_kg: float
    revenue: float
    direct_cost: float
    contribution: float


class OrchardScenario(Strict):
    revenue: float
    operating_expense: float
    operating_surplus: float
    labor_adjusted_earnings: float
    unpaid_labor: float
    equipment_purchases: float | None
    sold_kg: float
    break_even_price: float | None
    break_even_note: str
    shared_cost: float
    varieties: list[VarietyResult]


class OrchardResult(Strict):
    kind: Literal["orchard"] = "orchard"
    engine_version: str = "orchard-1"
    scenarios: dict[str, OrchardScenario]
    sensitivity: list[dict[str, Any]]
    checks: list[dict[str, Any]] = Field(default_factory=list)
    default_keys: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "假定全部销售款已收齐；为经营期总账，不代表逐月现金流。",
            "共用成本仅扣一次；品种贡献未分摊共用成本。",
            "未付酬家庭劳动单列估值，已支付人工不再重复扣除。",
            "设备购置单列，不含折旧、历史建园投入及多年回本测算。",
        ]
    )


def _scenario(
    params: OrchardParams, scenario: Scenario, override: tuple[int, float] | None = None
) -> OrchardScenario:
    def n(value):
        return override[1] if override and id(value) == override[0] else value.get(scenario)

    o = params.orchard
    rows = []
    total_revenue = total_direct = total_sold = total_channel_variable = 0.0
    for v in o.varieties.base:
        harvest = n(v.harvest_kg)
        saleable = harvest * (1 - n(v.loss_rate))
        revenue = sold = channel_cost = channel_variable = 0.0
        for g in v.grades:
            weight = saleable * g.share * n(g.sell_through)
            for c in g.channels:
                kg = weight * c.share
                sales = kg * n(c.price)
                variable = kg * (n(c.packaging_per_kg) + n(c.logistics_per_kg))
                sold += kg
                revenue += sales
                channel_variable += variable
                channel_cost += variable + sales * n(c.fee_rate)
        direct = channel_cost + sum(n(getattr(v.costs, k)) for k in DirectCosts.model_fields)
        rows.append(
            VarietyResult(
                id=v.id,
                name=v.name,
                harvest_kg=harvest,
                saleable_kg=saleable,
                sold_kg=sold,
                unsold_kg=saleable - sold,
                revenue=revenue,
                direct_cost=direct,
                contribution=revenue - direct,
            )
        )
        total_revenue += revenue
        total_direct += direct
        total_sold += sold
        total_channel_variable += channel_variable
    shared = sum(n(getattr(o.shared_costs.base, k)) for k in SharedCosts.model_fields)
    expense = total_direct + shared
    # 求等效统一均价：销售比例/费用率固定，收入扣费后覆盖非佣金成本。
    weighted_net_kg = sum(
        n(v.harvest_kg)
        * (1 - n(v.loss_rate))
        * g.share
        * n(g.sell_through)
        * c.share
        * (1 - n(c.fee_rate))
        for v in o.varieties.base
        for g in v.grades
        for c in g.channels
    )
    non_commission = (
        shared
        + total_channel_variable
        + sum(n(getattr(v.costs, k)) for v in o.varieties.base for k in DirectCosts.model_fields)
    )
    unpaid = n(o.unpaid_labor)
    return OrchardScenario(
        revenue=total_revenue,
        operating_expense=expense,
        operating_surplus=total_revenue - expense,
        labor_adjusted_earnings=total_revenue - expense - unpaid,
        unpaid_labor=unpaid,
        equipment_purchases=n(o.equipment) if o.equipment else None,
        sold_kg=total_sold,
        break_even_price=non_commission / weighted_net_kg if weighted_net_kg > 0 else None,
        break_even_note="按当前等级、渠道及售出量，统一售价覆盖经营支出所需的均价；未含家庭劳动估值。"
        if weighted_net_kg > 0
        else "无有效售出量或渠道费率为100%，无法求有限保本均价。",
        shared_cost=shared,
        varieties=rows,
    )


def _ranges(node, path=()):
    """遍历已验证模型；只覆盖一个值，无复制、无重复全量校验、无原地修改。"""
    if isinstance(node, ParamValue) and isinstance(node.base, (int, float)):
        for tier in ("pessimistic", "optimistic"):
            value = getattr(node, tier)
            if value is not None and value != node.base:
                yield path, node, tier, value
    elif isinstance(node, BaseModel):
        for key in type(node).model_fields:
            yield from _ranges(getattr(node, key), (*path, key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _ranges(value, (*path, i))


def evaluate_orchard(params: OrchardParams) -> OrchardResult:
    if missing := params.missing_keys():
        raise MissingParametersError(missing)
    scenarios = {s: _scenario(params, s) for s in SCENARIOS}
    sensitivity = []
    for path, value, tier, number in _ranges(params):
        result = _scenario(params, "base", (id(value), number))
        sensitivity.append(
            {
                "key": ".".join(map(str, path)),
                "scenario": tier,
                "delta": result.operating_surplus - scenarios["base"].operating_surplus,
            }
        )
    return OrchardResult(
        scenarios=scenarios,
        sensitivity=sorted(sensitivity, key=lambda x: abs(x["delta"]), reverse=True),
    )


class OrchardWhatIf(Strict):
    baseline: OrchardResult
    modified: OrchardResult
    surplus_delta: float


def orchard_what_if(params: OrchardParams, changes: Mapping[str, Any]) -> OrchardWhatIf:
    before, after = evaluate_orchard(params), evaluate_orchard(params.with_values(changes))
    return OrchardWhatIf(
        baseline=before,
        modified=after,
        surplus_delta=after.scenarios["base"].operating_surplus
        - before.scenarios["base"].operating_surplus,
    )
