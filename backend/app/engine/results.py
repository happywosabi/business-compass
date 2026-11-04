"""计算引擎的输出结构。

字段与数据结构文档第七节 evaluations.results 一一对应；
用 model_dump(mode="json") 即可存入评估快照。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .params import Scenario


class TierValues(BaseModel):
    """悲观 / 中性 / 乐观三档数值。"""

    pessimistic: float
    base: float
    optimistic: float


class MonthRow(BaseModel):
    """逐月数据的一行；t = 0 表示开业前，此时只有现金。"""

    t: int
    daily_orders: float | None
    revenue: float | None
    cash_flow: float | None
    cash: float


class CashLow(BaseModel):
    amount: float
    month: int


class StartupSummary(BaseModel):
    sunk: float  # 不可收回投入
    recoverable: float  # 可收回投入（押金 + 首批备货）
    total: float  # 启动投入合计


class ScenarioResult(BaseModel):
    """一个情景的测算结果。"""

    startup: StartupSummary
    fee_rate: float  # 比例费率 f
    unit_margin: float  # 每单毛利 m
    steady_monthly_revenue: float
    steady_fixed_cost: float  # 含老板工资
    steady_monthly_cash: float  # 含老板工资
    steady_monthly_cash_excl_owner: float
    first_profitable_month: int | None
    first_profitable_month_excl_owner: int | None
    cash_low: CashLow | None  # 稳定期仍亏损时为 None（准备多少钱都不够）
    suggested_funding: list[float] | None  # [加 2 个月固定成本, 加 3 个月固定成本]
    payback_month: int | None  # None 表示 120 个月内无法回本
    payback_month_excl_owner: int | None
    lease_months: int
    lease_check: Literal["pass", "fail"]
    cash_at_month_36: float  # 第 36 个月末手里的钱（敏感性分析的排序依据）
    monthly: list[MonthRow]  # 第 0 … 36 个月


class Threshold(BaseModel):
    """单变量临界值。value 为 None 表示不存在（如每单都亏钱时，卖多少都不能保本）。"""

    value: float | None
    headroom: float | None  # 临界值 ÷ 当前值 − 1；负数表示还能下降多少，正数表示还能上升多少


class PaybackRange(BaseModel):
    pessimistic: int | None
    base: int | None
    optimistic: int | None


class SensitivityItem(BaseModel):
    """一个参数的敏感性：只让它取悲观 / 乐观值，其他参数保持中性。"""

    key: str
    cash_at_month_36: TierValues
    downside: float  # 取悲观值时，第 36 个月末的钱比中性情景少多少（排序依据）
    swing: float  # 乐观值与悲观值之间相差多少
    payback_month: PaybackRange


class CheckResult(BaseModel):
    """一条合理性检查的结果。"""

    rule: str
    level: Literal["info", "warning"]
    message: str
    value: float | None = None
    threshold: float | None = None


class EvaluationResult(BaseModel):
    """一次完整评估的结果。"""

    engine_version: str
    scenarios: dict[Scenario, ScenarioResult]
    thresholds: dict[str, Threshold]
    safety_margin: float | None  # 客流再少百分之多少就开始亏
    sensitivity: list[SensitivityItem]  # 按"最怕"排序，第一个最怕
    checks: list[CheckResult]
    default_keys: list[str]  # 使用了默认值的参数

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.level == "warning"]


class WhatIfResult(BaseModel):
    """假设性测算：修改前后中性情景的对比，不保存。"""

    changed_keys: list[str]
    before: ScenarioResult
    after: ScenarioResult
