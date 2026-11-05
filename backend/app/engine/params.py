"""实体小店测算参数：三档参数值、参数清单和硬性校验。

对应文档：
- 商业档案数据结构 6.1（参数值的格式）、6.2（实体小店参数清单）
- 实体小店测算模型 第二节（参数含义）

这里只做"硬性校验"：数学上不允许的值（金额为负、比例超出 0–1 等）直接拒绝。
数值"是否合理"（如成本率偏低）属于合理性检查，见 checks.py。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Scenario = Literal["pessimistic", "base", "optimistic"]
SCENARIOS: tuple[Scenario, ...] = ("pessimistic", "base", "optimistic")

Source = Literal["user", "ai_inferred", "default", "experiment", "actual"]

T = TypeVar("T")


class ParamValue(BaseModel, Generic[T]):
    """一个参数的三档取值。

    悲观指对经营不利的方向：收入类取低值，成本类取高值。
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    base: T
    pessimistic: T | None = None
    optimistic: T | None = None
    source: Source = "user"
    note: str | None = None

    def get(self, scenario: Scenario = "base") -> T:
        """取某一档的值；悲观值或乐观值为空时等于中性值。"""
        if scenario == "base":
            return self.base
        value = getattr(self, scenario)
        return self.base if value is None else value

    @property
    def has_range(self) -> bool:
        """是否填了与中性值不同的悲观值或乐观值。"""
        return any(v is not None and v != self.base for v in (self.pessimistic, self.optimistic))


# ---------------------------------------------------------------------------
# 取值类型：在类型上直接写明硬性约束
# ---------------------------------------------------------------------------

NonNegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
Rate = Annotated[float, Field(ge=0, le=1)]
Count = Annotated[int, Field(ge=0)]
WholeMonths = Annotated[int, Field(ge=1)]
WholeYears = Annotated[int, Field(ge=1)]
CalendarMonth = Annotated[int, Field(ge=1, le=12)]
DaysPerMonth = Annotated[float, Field(gt=0, le=31)]
RampFactor = Annotated[float, Field(ge=0, le=2)]
SeasonFactor = Annotated[float, Field(ge=0)]
LocationType = Literal["mall", "street", "school", "residential", "office", "other"]


def _check_seasonality(values: list[float]) -> list[float]:
    if len(values) != 12:
        raise ValueError(f"季节系数必须正好 12 个，当前为 {len(values)} 个")
    mean = sum(values) / 12
    if abs(mean - 1) > 0.01:
        raise ValueError(f"季节系数的平均值必须为 1，当前为 {mean:.3f}")
    return values


class Channel(BaseModel):
    """一个销售渠道，如堂食、外卖、团购。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    share: Rate
    fee_rate: Rate


def _check_channels(channels: list[Channel]) -> list[Channel]:
    if channels:
        total = sum(c.share for c in channels)
        if abs(total - 1) > 0.01:
            raise ValueError(f"各渠道占比之和必须为 1，当前为 {total:.3f}")
    return channels


class StaffItem(BaseModel):
    """一类员工。"""

    model_config = ConfigDict(extra="forbid")

    role: str
    count: Count
    monthly_cost: NonNegative


Seasonality = Annotated[list[SeasonFactor], AfterValidator(_check_seasonality)]
Channels = Annotated[list[Channel], AfterValidator(_check_channels)]


# ---------------------------------------------------------------------------
# 参数清单（与数据结构文档 6.2 一一对应）
# ---------------------------------------------------------------------------


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartupParams(_Section):
    """启动投入（开业前一次性支出）。"""

    transfer_fee: ParamValue[NonNegative] | None = None
    renovation: ParamValue[NonNegative] | None = None
    equipment: ParamValue[NonNegative] | None = None
    licenses: ParamValue[NonNegative] | None = None
    opening_marketing: ParamValue[NonNegative] | None = None
    renovation_months: ParamValue[NonNegative] | None = None
    rent_free_months: ParamValue[NonNegative] | None = None
    deposit_months: ParamValue[NonNegative] | None = None
    initial_stock: ParamValue[NonNegative] | None = None


class RevenueParams(_Section):
    """收入。"""

    daily_orders: ParamValue[Positive] | None = None
    avg_ticket: ParamValue[Positive] | None = None
    open_days: ParamValue[DaysPerMonth] | None = None
    channels: ParamValue[Channels] | None = None
    opening_month: ParamValue[CalendarMonth] | None = None
    ramp: ParamValue[list[RampFactor]] | None = None
    seasonality: ParamValue[Seasonality] | None = None


class VariableCostParams(_Section):
    """变动成本（卖得越多花得越多）。"""

    unit_cost: ParamValue[NonNegative] | None = None
    payment_fee_rate: ParamValue[Rate] | None = None
    tax_rate: ParamValue[Rate] | None = None


class FixedCostParams(_Section):
    """固定成本（每月不管卖多少都要付）。"""

    rent: ParamValue[NonNegative] | None = None
    rent_increase_rate: ParamValue[Rate] | None = None
    rent_increase_every_years: ParamValue[WholeYears] | None = None
    staff: ParamValue[list[StaffItem]] | None = None
    owner_salary: ParamValue[NonNegative] | None = None
    utilities: ParamValue[NonNegative] | None = None
    other_fixed: ParamValue[NonNegative] | None = None


class StoreParams(_Section):
    """门店。"""

    location_type: ParamValue[LocationType] | None = None
    area_sqm: ParamValue[Positive] | None = None
    seats: ParamValue[Count] | None = None
    turns_per_day: ParamValue[NonNegative] | None = None
    delivery_capacity: ParamValue[NonNegative] | None = None
    lease_months: ParamValue[WholeMonths] | None = None


SECTIONS: dict[str, type[_Section]] = {
    "startup": StartupParams,
    "revenue": RevenueParams,
    "variable_cost": VariableCostParams,
    "fixed_cost": FixedCostParams,
    "store": StoreParams,
}

# 不影响测算的参数：只用于合理性检查（面积、座位等）和展示
OPTIONAL_KEYS = frozenset(
    {
        "store.location_type",
        "store.area_sqm",
        "store.seats",
        "store.turns_per_day",
        "store.delivery_capacity",
    }
)

ALL_KEYS: tuple[str, ...] = tuple(
    f"{section}.{name}" for section, model in SECTIONS.items() for name in model.model_fields
)
REQUIRED_KEYS: tuple[str, ...] = tuple(k for k in ALL_KEYS if k not in OPTIONAL_KEYS)


class MissingParametersError(ValueError):
    """测算所需的参数不完整。`keys` 是缺失参数的清单。"""

    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        super().__init__("缺少参数：" + "、".join(self.keys))


def _split_key(key: str) -> tuple[str, str]:
    if key not in ALL_KEYS:
        raise KeyError(f"未知参数：{key}")
    section, name = key.split(".", 1)
    return section, name


def _to_param_dict(value: Any) -> dict[str, Any] | None:
    """把各种写法统一成参数值字典：可以传 ParamValue、带 base 的字典，或直接传一个值。"""
    if value is None:
        return None
    if isinstance(value, ParamValue):
        return value.model_dump()
    if isinstance(value, Mapping) and "base" in value:
        return dict(value)
    return {"base": value}


class PhysicalStoreParams(BaseModel):
    """实体小店的全部测算参数（档案里的 parameters 字段）。

    参数可以逐步填写，所以每一项都允许为空；测算前用 missing_keys() 检查是否齐全。
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    startup: StartupParams = Field(default_factory=StartupParams)
    revenue: RevenueParams = Field(default_factory=RevenueParams)
    variable_cost: VariableCostParams = Field(default_factory=VariableCostParams)
    fixed_cost: FixedCostParams = Field(default_factory=FixedCostParams)
    store: StoreParams = Field(default_factory=StoreParams)
    # 客流估算的原始输入（选址法、对标法），只做记录，不参与测算
    traffic_estimates: dict[str, Any] | None = None

    def get(self, key: str) -> ParamValue[Any] | None:
        """按 "分组.参数名" 取参数，如 get("revenue.daily_orders")。"""
        section, name = _split_key(key)
        return getattr(getattr(self, section), name)

    def missing_keys(self) -> list[str]:
        """测算必需、但还没有填写的参数。"""
        return [k for k in REQUIRED_KEYS if self.get(k) is None]

    def keys_with_range(self) -> list[str]:
        """填了悲观值或乐观值（且与中性值不同）的测算参数。"""
        return [k for k in REQUIRED_KEYS if (pv := self.get(k)) is not None and pv.has_range]

    def keys_by_source(self, source: Source) -> list[str]:
        """来源为指定值的参数，如所有使用默认值的参数。"""
        return [k for k in ALL_KEYS if (pv := self.get(k)) is not None and pv.source == source]

    def with_values(self, changes: Mapping[str, Any]) -> PhysicalStoreParams:
        """返回修改后的新参数（原参数不变），修改结果会重新校验。

        changes 的值可以是 ParamValue、带 base 的字典、直接的值（视为中性值），或 None（清空）。
        """
        data = self.model_dump()
        for key, value in changes.items():
            section, name = _split_key(key)
            data[section][name] = _to_param_dict(value)
        return PhysicalStoreParams.model_validate(data)
