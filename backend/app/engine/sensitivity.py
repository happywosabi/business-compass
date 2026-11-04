"""敏感性分析：找出"最怕的变量"。

对应文档：实体小店测算模型 第六节、代码结构 2.5。

每次只让一个参数取悲观值 / 乐观值，其他保持中性，
按"第 36 个月末手里的钱"在悲观时下降多少排序：
它同时反映启动投入（如装修超支）和每月盈亏（如客流不足），而且一定有数值。
"""

from __future__ import annotations

from .inputs import build_inputs
from .params import PhysicalStoreParams
from .projection import project
from .results import PaybackRange, SensitivityItem, TierValues

SENSITIVITY_MONTH = 36


def run_sensitivity(params: PhysicalStoreParams) -> list[SensitivityItem]:
    """对所有填了三档的测算参数做敏感性分析，最怕的排在最前。"""
    base = project(build_inputs(params, "base"))
    base_cash = base.cash_at(SENSITIVITY_MONTH)

    items: list[SensitivityItem] = []
    for key in params.keys_with_range():
        pessimistic = project(build_inputs(params, "base", {key: "pessimistic"}))
        optimistic = project(build_inputs(params, "base", {key: "optimistic"}))
        pessimistic_cash = pessimistic.cash_at(SENSITIVITY_MONTH)
        optimistic_cash = optimistic.cash_at(SENSITIVITY_MONTH)
        items.append(
            SensitivityItem(
                key=key,
                cash_at_month_36=TierValues(
                    pessimistic=pessimistic_cash, base=base_cash, optimistic=optimistic_cash
                ),
                downside=base_cash - pessimistic_cash,
                swing=optimistic_cash - pessimistic_cash,
                payback_month=PaybackRange(
                    pessimistic=pessimistic.payback_month,
                    base=base.payback_month,
                    optimistic=optimistic.payback_month,
                ),
            )
        )

    items.sort(key=lambda item: (item.downside, item.swing), reverse=True)
    return items
