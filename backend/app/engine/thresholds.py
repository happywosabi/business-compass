"""单变量临界值和安全边际。

对应文档：实体小店测算模型 3.4。按稳定期计算（爬坡 = 1、季节 = 1、基础房租），含老板工资：

    保本日单量     N*    = F ÷ (m × D)
    保本客单价     P*    = (F ÷ (N × D) + c) ÷ (1 − f)
    临界按单成本   c*    = P × (1 − f) − F ÷ (N × D)
    临界房租       房租* = N × D × m − (F − 房租)
    安全边际             = (N − N*) ÷ N
"""

from __future__ import annotations

from .inputs import ScenarioInputs
from .results import Threshold


def _threshold(value: float | None, current: float) -> Threshold:
    if value is None:
        return Threshold(value=None, headroom=None)
    headroom = value / current - 1 if current > 0 else None
    return Threshold(value=value, headroom=headroom)


def compute_thresholds(inputs: ScenarioInputs) -> tuple[dict[str, Threshold], float | None]:
    """返回 (各参数的临界值, 安全边际)。"""
    fixed = inputs.steady_fixed_cost()
    n, d, p = inputs.daily_orders, inputs.open_days, inputs.avg_ticket
    c, f, m = inputs.unit_cost, inputs.fee_rate, inputs.unit_margin
    fixed_per_order = fixed / (n * d)

    # 每单毛利不为正时，卖多少都不能保本
    orders = fixed / (m * d) if m > 0 else None
    # 比例费率达到 100% 时，定价多高都不能保本
    ticket = (fixed_per_order + c) / (1 - f) if f < 1 else None
    # 结果为负表示：成本降到 0、房租降到 0 也不能保本
    cost = p * (1 - f) - fixed_per_order
    rent = n * d * m - (fixed - inputs.base_rent)

    thresholds = {
        "revenue.daily_orders": _threshold(orders, n),
        "revenue.avg_ticket": _threshold(ticket, p),
        "variable_cost.unit_cost": _threshold(cost if cost >= 0 else None, c),
        "fixed_cost.rent": _threshold(rent if rent >= 0 else None, inputs.base_rent),
    }
    safety_margin = (n - orders) / n if orders is not None else None
    return thresholds, safety_margin
