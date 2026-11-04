"""逐月推演现金曲线。

对应文档：实体小店测算模型 3.2（逐月推演）、3.3（输出指标）。

    现金(0) = − 启动投入
    π(t)    = N(t) × D × m − F(t)
    现金(t) = 现金(t − 1) + π(t)
"""

from __future__ import annotations

from dataclasses import dataclass

from .inputs import ScenarioInputs

MAX_MONTHS = 120  # 计算回本时最多推演 120 个月

# 浮点数计算会有极小的误差（如 0.1 + 0.2 ≠ 0.3），比较时留一点余量
_EPSILON = 1e-6


@dataclass(frozen=True)
class MonthCash:
    """某个月的推演结果。"""

    t: int
    daily_orders: float  # 当月日均单量 N(t)
    revenue: float  # 当月营业额
    cash_flow: float  # 当月现金流 π(t)
    cash: float  # 月末累计现金 现金(t)


@dataclass(frozen=True)
class Projection:
    """一条现金曲线及从中读出的指标。"""

    initial_cash: float  # 现金(0) = − 启动投入
    months: tuple[MonthCash, ...]  # 第 1 … MAX_MONTHS 个月
    first_profitable_month: int | None  # 第一个 π(t) ≥ 0 的月份
    payback_month: int | None  # 累计现金流首次覆盖不可收回投入的月份
    cash_low_amount: float  # 现金最低点
    cash_low_month: int  # 最低点出现在第几个月（0 表示开业前）

    def cash_at(self, t: int) -> float:
        """第 t 个月末的累计现金；t = 0 为开业前。"""
        return self.initial_cash if t == 0 else self.months[t - 1].cash


def project(
    inputs: ScenarioInputs, include_owner: bool = True, months: int = MAX_MONTHS
) -> Projection:
    """逐月推演。include_owner=False 时不计老板工资。"""
    cash = -inputs.startup_investment
    initial_cash = cash
    cumulative_flow = 0.0
    first_profitable: int | None = None
    payback: int | None = None
    low_amount, low_month = cash, 0
    rows: list[MonthCash] = []

    for t in range(1, months + 1):
        daily = inputs.daily_orders_in_month(t)
        monthly_orders = daily * inputs.open_days
        cash_flow = monthly_orders * inputs.unit_margin - inputs.fixed_cost(t, include_owner)
        cash += cash_flow
        cumulative_flow += cash_flow

        if first_profitable is None and cash_flow >= -_EPSILON:
            first_profitable = t
        # 押金和备货可以收回，所以回本只需覆盖不可收回投入
        if payback is None and cumulative_flow >= inputs.sunk_investment - _EPSILON:
            payback = t
        if cash < low_amount:
            low_amount, low_month = cash, t

        rows.append(
            MonthCash(
                t=t,
                daily_orders=daily,
                revenue=monthly_orders * inputs.avg_ticket,
                cash_flow=cash_flow,
                cash=cash,
            )
        )

    return Projection(
        initial_cash=initial_cash,
        months=tuple(rows),
        first_profitable_month=first_profitable,
        payback_month=payback,
        cash_low_amount=low_amount,
        cash_low_month=low_month,
    )
