"""合理性检查。

对应文档：实体小店测算模型 第四节、AI 访谈流程 第九节。

检查只给出提醒，不阻止测算。阈值由调用方传入（来自 templates/*/checks.yaml），
某项阈值为空时跳过对应检查。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .inputs import ScenarioInputs
from .results import CheckResult


class CheckRules(BaseModel):
    """某个业态的经验阈值。"""

    model_config = ConfigDict(extra="forbid")

    cost_ratio_min: float | None = None  # 按单成本占售价的常见下限
    cost_ratio_max: float | None = None  # 按单成本占售价的常见上限
    rent_ratio_max: float | None = None  # 房租占营业额的上限
    labor_ratio_max: float | None = None  # 员工工资占营业额的上限
    max_orders_per_staff_per_day: float | None = None  # 每人每天最多能做多少单
    ramp_first_month_max: float | None = None  # 开业第一个月最多达到稳定期的多少
    revenue_per_sqm_month_max: float | None = None  # 每平米每月营业额上限


def _info(rule: str, message: str, value: float | None = None, threshold: float | None = None):
    return CheckResult(rule=rule, level="info", message=message, value=value, threshold=threshold)


def _warning(rule: str, message: str, value: float | None = None, threshold: float | None = None):
    return CheckResult(
        rule=rule, level="warning", message=message, value=value, threshold=threshold
    )


def _check_unit_margin(inputs: ScenarioInputs) -> CheckResult:
    m = inputs.unit_margin
    if m <= 0:
        return _warning(
            "unit_margin",
            f"扣掉原料包装和各项费用后，每单毛利为 {m:.2f} 元，每卖一单都在亏钱",
            value=m,
        )
    return _info("unit_margin", f"每单毛利 {m:.2f} 元", value=m)


def _check_cost_ratio(inputs: ScenarioInputs, rules: CheckRules) -> CheckResult | None:
    low, high = rules.cost_ratio_min, rules.cost_ratio_max
    if low is None or high is None:
        return None
    ratio = inputs.unit_cost / inputs.avg_ticket
    common = f"同类店一般在 {low:.0%}–{high:.0%}"
    if ratio < low:
        return _warning(
            "cost_ratio",
            f"按单成本占售价 {ratio:.0%}，{common}，可能偏低，建议核实原料和包装报价",
            value=ratio,
            threshold=low,
        )
    if ratio > high:
        return _warning(
            "cost_ratio",
            f"按单成本占售价 {ratio:.0%}，{common}，偏高，每单利润会被压缩",
            value=ratio,
            threshold=high,
        )
    return _info("cost_ratio", f"按单成本占售价 {ratio:.0%}，在常见范围内", value=ratio)


def _check_rent_ratio(inputs: ScenarioInputs, rules: CheckRules) -> CheckResult | None:
    limit = rules.rent_ratio_max
    if limit is None:
        return None
    ratio = inputs.base_rent / inputs.steady_monthly_revenue
    if ratio > limit:
        return _warning(
            "rent_ratio",
            f"房租占营业额 {ratio:.0%}，同类店一般不超过 {limit:.0%}",
            value=ratio,
            threshold=limit,
        )
    return _info("rent_ratio", f"房租占营业额 {ratio:.0%}，在常见范围内", value=ratio)


def _check_labor_ratio(inputs: ScenarioInputs, rules: CheckRules) -> CheckResult | None:
    limit = rules.labor_ratio_max
    if limit is None:
        return None
    ratio = inputs.staff_cost / inputs.steady_monthly_revenue
    if ratio > limit:
        return _warning(
            "labor_ratio",
            f"员工工资占营业额 {ratio:.0%}，同类店一般不超过 {limit:.0%}",
            value=ratio,
            threshold=limit,
        )
    return _info("labor_ratio", f"员工工资占营业额 {ratio:.0%}，在常见范围内", value=ratio)


def _check_orders_per_staff(inputs: ScenarioInputs, rules: CheckRules) -> CheckResult | None:
    # 老板工资大于 0 表示老板在店里干活，算一个人手
    hands = inputs.staff_count + (1 if inputs.owner_salary > 0 else 0)
    if hands == 0:
        return _warning("orders_per_staff", "没有安排任何人手：员工为 0，老板也不在店里干活")
    limit = rules.max_orders_per_staff_per_day
    if limit is None:
        return None
    per_person = inputs.daily_orders / hands
    if per_person > limit:
        return _warning(
            "orders_per_staff",
            f"平均每人每天要做 {per_person:.0f} 单，同类店一般不超过 {limit:.0f} 单，高峰期可能忙不过来",
            value=per_person,
            threshold=limit,
        )
    return _info(
        "orders_per_staff", f"平均每人每天约 {per_person:.0f} 单，人手够用", value=per_person
    )


def _check_capacity(inputs: ScenarioInputs) -> CheckResult | None:
    capacity = inputs.capacity
    if capacity is None:
        return None
    if inputs.daily_orders > capacity:
        return _warning(
            "capacity",
            f"按座位、翻台和外卖出餐能力估算，每天最多接待约 {capacity:.0f} 单，"
            f"预计的 {inputs.daily_orders:.0f} 单超出了接待能力",
            value=inputs.daily_orders,
            threshold=capacity,
        )
    return _info(
        "capacity", f"预计单量在接待能力（约 {capacity:.0f} 单）以内", value=inputs.daily_orders
    )


def _check_ramp(inputs: ScenarioInputs, rules: CheckRules) -> CheckResult | None:
    limit = rules.ramp_first_month_max
    if limit is None:
        return None
    first = inputs.ramp_factor(1)
    if first > limit:
        return _warning(
            "ramp_first_month",
            f"假设开业第一个月就达到稳定期的 {first:.0%}，新店通常需要几个月爬坡，可能过于乐观",
            value=first,
            threshold=limit,
        )
    return _info("ramp_first_month", f"开业第一个月按稳定期的 {first:.0%} 计算", value=first)


def _check_revenue_per_sqm(inputs: ScenarioInputs, rules: CheckRules) -> CheckResult | None:
    limit = rules.revenue_per_sqm_month_max
    if limit is None or inputs.area_sqm is None:
        return None
    per_sqm = inputs.steady_monthly_revenue / inputs.area_sqm
    if per_sqm > limit:
        return _warning(
            "revenue_per_sqm",
            f"每平米每月营业额约 {per_sqm:,.0f} 元，明显高于同类店（一般不超过 {limit:,.0f} 元）",
            value=per_sqm,
            threshold=limit,
        )
    return _info("revenue_per_sqm", f"每平米每月营业额约 {per_sqm:,.0f} 元", value=per_sqm)


def run_checks(inputs: ScenarioInputs, rules: CheckRules) -> list[CheckResult]:
    """对一个情景（通常是中性情景）运行全部检查。"""
    results = [
        _check_unit_margin(inputs),
        _check_cost_ratio(inputs, rules),
        _check_rent_ratio(inputs, rules),
        _check_labor_ratio(inputs, rules),
        _check_orders_per_staff(inputs, rules),
        _check_capacity(inputs),
        _check_ramp(inputs, rules),
        _check_revenue_per_sqm(inputs, rules),
    ]
    return [r for r in results if r is not None]
