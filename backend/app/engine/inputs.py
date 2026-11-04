"""把三档参数转换成某一个情景的计算输入，并计算推导值。

对应文档：实体小店测算模型 第二节（参数）、3.2（逐月推演中用到的公式）。

推导值（押金金额、装修期房租、比例费率 f、每月固定成本 F 等）只在这里计算，不存入档案。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .params import ALL_KEYS, MissingParametersError, PhysicalStoreParams, Scenario


@dataclass(frozen=True)
class ScenarioInputs:
    """某一个情景下、所有参数都已确定为具体数值的计算输入。"""

    # 启动投入
    transfer_fee: float
    renovation: float
    equipment: float
    licenses: float
    opening_marketing: float
    renovation_months: float
    rent_free_months: float
    deposit_months: float
    initial_stock: float
    # 收入
    daily_orders: float
    avg_ticket: float
    open_days: float
    channel_fee_rate: float  # 各渠道平台费率按占比加权后的合计
    opening_month: int
    ramp: tuple[float, ...]
    seasonality: tuple[float, ...]
    # 变动成本
    unit_cost: float
    payment_fee_rate: float
    tax_rate: float
    # 固定成本
    base_rent: float
    rent_increase_rate: float
    rent_increase_every_years: int
    staff_count: int
    staff_cost: float
    owner_salary: float
    utilities: float
    other_fixed: float
    # 门店
    lease_months: int
    area_sqm: float | None = None
    seats: int | None = None
    turns_per_day: float | None = None
    delivery_capacity: float | None = None

    # ---- 启动投入 ----

    @property
    def deposit(self) -> float:
        """房租押金 = 押金月数 × 月租。"""
        return self.deposit_months * self.base_rent

    @property
    def renovation_rent(self) -> float:
        """装修期房租 = max(装修月数 − 免租月数, 0) × 月租。"""
        return max(self.renovation_months - self.rent_free_months, 0) * self.base_rent

    @property
    def sunk_investment(self) -> float:
        """不可收回投入。"""
        return (
            self.transfer_fee
            + self.renovation
            + self.equipment
            + self.licenses
            + self.opening_marketing
            + self.renovation_rent
        )

    @property
    def recoverable_investment(self) -> float:
        """可收回投入：押金 + 首批备货。"""
        return self.deposit + self.initial_stock

    @property
    def startup_investment(self) -> float:
        """启动投入合计。"""
        return self.sunk_investment + self.recoverable_investment

    # ---- 单位经济 ----

    @property
    def fee_rate(self) -> float:
        """比例费率 f = 渠道加权平台费率 + 支付手续费率 + 综合税费率。"""
        return self.channel_fee_rate + self.payment_fee_rate + self.tax_rate

    @property
    def unit_margin(self) -> float:
        """每单毛利 m = P × (1 − f) − c。"""
        return self.avg_ticket * (1 - self.fee_rate) - self.unit_cost

    # ---- 固定成本 ----

    def rent(self, t: int) -> float:
        """第 t 个月的房租：每满 k 年递增一次。"""
        periods = (t - 1) // (12 * self.rent_increase_every_years)
        return self.base_rent * (1 + self.rent_increase_rate) ** periods

    def _fixed_cost_with_rent(self, rent: float, include_owner: bool) -> float:
        owner = self.owner_salary if include_owner else 0.0
        return rent + self.staff_cost + owner + self.utilities + self.other_fixed

    def fixed_cost(self, t: int, include_owner: bool = True) -> float:
        """第 t 个月的固定成本 F(t)。"""
        return self._fixed_cost_with_rent(self.rent(t), include_owner)

    def steady_fixed_cost(self, include_owner: bool = True) -> float:
        """稳定期（按基础房租）的每月固定成本 F。"""
        return self._fixed_cost_with_rent(self.base_rent, include_owner)

    # ---- 单量 ----

    def ramp_factor(self, t: int) -> float:
        """第 t 个月的爬坡系数；爬坡列表之后为 1。"""
        return self.ramp[t - 1] if t <= len(self.ramp) else 1.0

    def season_factor(self, t: int) -> float:
        """第 t 个月的季节系数：第 t 个月对应的自然月 = (开业月份 + t − 2) mod 12 + 1。"""
        return self.seasonality[(self.opening_month + t - 2) % 12]

    def daily_orders_in_month(self, t: int) -> float:
        """第 t 个月的日均单量 N(t) = N × 爬坡系数 × 季节系数。"""
        return self.daily_orders * self.ramp_factor(t) * self.season_factor(t)

    # ---- 稳定期 ----

    @property
    def steady_monthly_revenue(self) -> float:
        """稳定期每月营业额 = N × D × P。"""
        return self.daily_orders * self.open_days * self.avg_ticket

    def steady_monthly_cash(self, include_owner: bool = True) -> float:
        """稳定期每月现金流（爬坡系数 = 1、季节系数 = 1、基础房租）。"""
        return self.daily_orders * self.open_days * self.unit_margin - self.steady_fixed_cost(
            include_owner
        )

    # ---- 产能 ----

    @property
    def capacity(self) -> float | None:
        """每日最大接待能力 = 座位数 × 翻台次数 + 外卖出餐能力；没有座位和翻台数据时为 None。"""
        if self.seats is None or self.turns_per_day is None:
            return None
        return self.seats * self.turns_per_day + (self.delivery_capacity or 0.0)


def build_inputs(
    params: PhysicalStoreParams,
    scenario: Scenario = "base",
    overrides: Mapping[str, Scenario] | None = None,
) -> ScenarioInputs:
    """取出某一情景下的计算输入。

    overrides 用于敏感性分析：指定个别参数取另一档的值，例如
    build_inputs(params, "base", {"revenue.daily_orders": "pessimistic"})。

    参数不完整时抛出 MissingParametersError，不做任何猜测。
    """
    missing = params.missing_keys()
    if missing:
        raise MissingParametersError(missing)

    overrides = dict(overrides or {})
    unknown = [k for k in overrides if k not in ALL_KEYS]
    if unknown:
        raise KeyError(f"未知参数：{'、'.join(unknown)}")

    def value(key: str):
        pv = params.get(key)
        if pv is None:
            return None
        return pv.get(overrides.get(key, scenario))

    channels = value("revenue.channels")
    staff = value("fixed_cost.staff")

    return ScenarioInputs(
        transfer_fee=value("startup.transfer_fee"),
        renovation=value("startup.renovation"),
        equipment=value("startup.equipment"),
        licenses=value("startup.licenses"),
        opening_marketing=value("startup.opening_marketing"),
        renovation_months=value("startup.renovation_months"),
        rent_free_months=value("startup.rent_free_months"),
        deposit_months=value("startup.deposit_months"),
        initial_stock=value("startup.initial_stock"),
        daily_orders=value("revenue.daily_orders"),
        avg_ticket=value("revenue.avg_ticket"),
        open_days=value("revenue.open_days"),
        channel_fee_rate=sum(c.share * c.fee_rate for c in channels),
        opening_month=value("revenue.opening_month"),
        ramp=tuple(value("revenue.ramp")),
        seasonality=tuple(value("revenue.seasonality")),
        unit_cost=value("variable_cost.unit_cost"),
        payment_fee_rate=value("variable_cost.payment_fee_rate"),
        tax_rate=value("variable_cost.tax_rate"),
        base_rent=value("fixed_cost.rent"),
        rent_increase_rate=value("fixed_cost.rent_increase_rate"),
        rent_increase_every_years=value("fixed_cost.rent_increase_every_years"),
        staff_count=sum(s.count for s in staff),
        staff_cost=sum(s.count * s.monthly_cost for s in staff),
        owner_salary=value("fixed_cost.owner_salary"),
        utilities=value("fixed_cost.utilities"),
        other_fixed=value("fixed_cost.other_fixed"),
        lease_months=value("store.lease_months"),
        area_sqm=value("store.area_sqm"),
        seats=value("store.seats"),
        turns_per_day=value("store.turns_per_day"),
        delivery_capacity=value("store.delivery_capacity"),
    )
