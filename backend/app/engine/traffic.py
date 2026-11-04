"""客流估算：用三种方法估算日均单量。

对应文档：实体小店测算模型 第五节、AI 访谈流程 第五节。

估算结果只是给用户参考，确认后才写入"日均单量"参数。
"""

from __future__ import annotations

import statistics
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .params import SCENARIOS
from .results import TierValues

TrafficMethod = Literal["location", "benchmark", "capacity"]

_Rate = Annotated[float, Field(ge=0, le=1)]
_PositiveRate = Annotated[float, Field(gt=0, le=1)]


class TrafficDefaults(BaseModel):
    """某个业态的客流估算默认值（用户不知道时使用）。"""

    model_config = ConfigDict(extra="forbid")

    entry_rate: TierValues  # 路过的人中有多少进店
    conversion_rate: TierValues  # 进店的人中有多少买单
    day_factor: TierValues  # 高峰一小时的单量 × 这个系数 ≈ 全天单量
    delivery_share: TierValues  # 同类店外卖占总单量的比例；悲观取高值（推算出的总单量更少）


class LocationInputs(BaseModel):
    """选址法：去门口数路过的人。"""

    model_config = ConfigDict(extra="forbid")

    peak_hourly_passersby: Annotated[float, Field(ge=0)]
    entry_rate: _Rate | None = None
    conversion_rate: _Rate | None = None
    day_factor: Annotated[float, Field(gt=0)] | None = None


class BenchmarkStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    monthly_delivery_sales: Annotated[float, Field(ge=0)]  # 外卖平台显示的月销量
    delivery_share: _PositiveRate | None = None  # 这家店外卖占总单量的比例（知道的话）


class BenchmarkInputs(BaseModel):
    """对标法：看附近同类店的外卖月销量。"""

    model_config = ConfigDict(extra="forbid")

    stores: Annotated[list[BenchmarkStore], Field(min_length=1)]


class CapacityInputs(BaseModel):
    """产能反推：座位数 × 翻台次数 + 外卖出餐能力。"""

    model_config = ConfigDict(extra="forbid")

    seats: Annotated[int, Field(ge=0)]
    turns_per_day: Annotated[float, Field(ge=0)]
    delivery_capacity: Annotated[float, Field(ge=0)] = 0


class TrafficEstimate(BaseModel):
    method: TrafficMethod
    pessimistic: float
    base: float
    optimistic: float
    is_upper_bound: bool = False  # 产能反推得到的是上限，不是预期
    used_defaults: list[str] = []  # 使用了哪些业态默认值
    note: str


def _location(data: dict[str, Any], defaults: TrafficDefaults) -> TrafficEstimate:
    inputs = LocationInputs.model_validate(data)
    used: list[str] = []
    tiers: dict[str, float] = {}
    for scenario in SCENARIOS:
        factors = []
        for name in ("entry_rate", "conversion_rate", "day_factor"):
            given = getattr(inputs, name)
            if given is None:
                if name not in used:
                    used.append(name)
                factors.append(getattr(getattr(defaults, name), scenario))
            else:
                factors.append(given)
        entry, conversion, day = factors
        tiers[scenario] = inputs.peak_hourly_passersby * entry * conversion * day
    return TrafficEstimate(
        method="location",
        **tiers,
        used_defaults=used,
        note="按高峰时段每小时路过人数 × 进店率 × 成交率 × 全天换算系数估算",
    )


def _benchmark(data: dict[str, Any], defaults: TrafficDefaults) -> TrafficEstimate:
    inputs = BenchmarkInputs.model_validate(data)
    used: list[str] = []
    per_store: dict[str, list[float]] = {s: [] for s in SCENARIOS}
    for store in inputs.stores:
        if store.delivery_share is None and "delivery_share" not in used:
            used.append("delivery_share")
        for scenario in SCENARIOS:
            share = store.delivery_share or getattr(defaults.delivery_share, scenario)
            per_store[scenario].append(store.monthly_delivery_sales / 30 / share)
    return TrafficEstimate(
        method="benchmark",
        pessimistic=min(per_store["pessimistic"]),
        base=statistics.median(per_store["base"]),
        optimistic=max(per_store["optimistic"]),
        used_defaults=used,
        note="按同类店外卖月销量 ÷ 30 天 ÷ 外卖占比估算；同类店多是已经稳定的老店，新店达到这个水平需要时间",
    )


def _capacity(data: dict[str, Any]) -> TrafficEstimate:
    inputs = CapacityInputs.model_validate(data)
    upper = inputs.seats * inputs.turns_per_day + inputs.delivery_capacity
    return TrafficEstimate(
        method="capacity",
        pessimistic=upper,
        base=upper,
        optimistic=upper,
        is_upper_bound=True,
        note="这是每天最多能接待的单量（上限），不是预期销量",
    )


def estimate_traffic(
    method: TrafficMethod, inputs: dict[str, Any], defaults: TrafficDefaults
) -> TrafficEstimate:
    """估算日均单量。inputs 的字段见 LocationInputs / BenchmarkInputs / CapacityInputs。"""
    if method == "location":
        return _location(inputs, defaults)
    if method == "benchmark":
        return _benchmark(inputs, defaults)
    if method == "capacity":
        return _capacity(inputs)
    raise ValueError(f"未知的估算方法：{method}")
