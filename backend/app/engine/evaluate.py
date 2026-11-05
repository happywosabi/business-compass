"""计算引擎的总入口。

evaluate：三种情景 → 逐月推演 → 临界值 → 敏感性 → 合理性检查 → 组装结果
what_if ：在当前参数上做临时修改，对比修改前后的中性情景，不保存
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .checks import CheckRules, run_checks
from .inputs import ScenarioInputs, build_inputs
from .params import SCENARIOS, PhysicalStoreParams
from .projection import project
from .results import (
    CashLow,
    EvaluationResult,
    MonthRow,
    ScenarioResult,
    StartupSummary,
    WhatIfResult,
)
from .sensitivity import SENSITIVITY_MONTH, run_sensitivity
from .thresholds import compute_thresholds
from .version import ENGINE_VERSION

DISPLAY_MONTHS = 36  # 结果中保存前 36 个月的逐月数据
CUSHION_MONTHS = (2, 3)  # 建议准备资金 = 现金最低点 + 2–3 个月固定成本


def scenario_result(inputs: ScenarioInputs) -> ScenarioResult:
    """计算一个情景的全部指标。"""
    with_owner = project(inputs, include_owner=True)
    without_owner = project(inputs, include_owner=False)
    fixed = inputs.steady_fixed_cost()
    steady_cash = inputs.steady_monthly_cash()

    if steady_cash > 0:
        # 资金建议与展示窗口一致；120 个月推演仅用于寻找回本月份。
        display_low = min(
            [(0, with_owner.initial_cash)]
            + [(m.t, m.cash) for m in with_owner.months[:DISPLAY_MONTHS]],
            key=lambda row: row[1],
        )
        cash_low = CashLow(amount=display_low[1], month=display_low[0])
        need = max(-display_low[1], 0.0)
        funding = [need + months * fixed for months in CUSHION_MONTHS]
    else:
        # 稳定期仍在亏钱：现金会一直减少，准备多少钱都不够
        cash_low, funding = None, None

    payback = with_owner.payback_month
    lease_ok = payback is not None and payback <= inputs.lease_months

    monthly = [
        MonthRow(t=0, daily_orders=None, revenue=None, cash_flow=None, cash=with_owner.initial_cash)
    ]
    monthly += [
        MonthRow(
            t=m.t,
            daily_orders=m.daily_orders,
            revenue=m.revenue,
            cash_flow=m.cash_flow,
            cash=m.cash,
        )
        for m in with_owner.months[:DISPLAY_MONTHS]
    ]

    return ScenarioResult(
        startup=StartupSummary(
            sunk=inputs.sunk_investment,
            recoverable=inputs.recoverable_investment,
            total=inputs.startup_investment,
        ),
        fee_rate=inputs.fee_rate,
        unit_margin=inputs.unit_margin,
        steady_monthly_revenue=inputs.steady_monthly_revenue,
        steady_fixed_cost=fixed,
        steady_monthly_cash=steady_cash,
        steady_monthly_cash_excl_owner=inputs.steady_monthly_cash(include_owner=False),
        first_profitable_month=with_owner.first_profitable_month,
        first_profitable_month_excl_owner=without_owner.first_profitable_month,
        cash_low=cash_low,
        suggested_funding=funding,
        payback_month=payback,
        payback_month_excl_owner=without_owner.payback_month,
        lease_months=inputs.lease_months,
        lease_check="pass" if lease_ok else "fail",
        cash_at_month_36=with_owner.cash_at(SENSITIVITY_MONTH),
        monthly=monthly,
    )


def evaluate(params: PhysicalStoreParams, rules: CheckRules | None = None) -> EvaluationResult:
    """完整评估。参数不完整时抛出 MissingParametersError（其中的 keys 为缺失清单）。"""
    rules = rules or CheckRules()
    scenarios = {s: scenario_result(build_inputs(params, s)) for s in SCENARIOS}
    base_inputs = build_inputs(params, "base")
    thresholds, safety_margin = compute_thresholds(base_inputs)
    return EvaluationResult(
        engine_version=ENGINE_VERSION,
        scenarios=scenarios,
        thresholds=thresholds,
        safety_margin=safety_margin,
        sensitivity=run_sensitivity(params),
        checks=run_checks(base_inputs, rules),
        default_keys=params.keys_by_source("default"),
    )


def what_if(params: PhysicalStoreParams, changes: Mapping[str, Any]) -> WhatIfResult:
    """假设性测算，例如 what_if(params, {"fixed_cost.rent": 10000})。不修改原参数。"""
    changed = params.with_values(changes)
    return WhatIfResult(
        changed_keys=list(changes),
        before=scenario_result(build_inputs(params, "base")),
        after=scenario_result(build_inputs(changed, "base")),
    )
