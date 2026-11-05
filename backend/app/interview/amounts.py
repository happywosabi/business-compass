"""访谈单位校验与确定性换算，不根据裸数字猜测销量或薪资。"""

import re
from decimal import Decimal


def guard_changes(changes: dict, user_text: str, previous_reply: str, *, converting=False) -> None:
    changes = {key: value for key, value in changes.items() if value is not None}
    if "revenue.daily_orders" in changes:
        explicit_orders = re.search(r"单量|销量|卖|售|订单|杯|\d\s*单(?!位|价)", user_text)
        if re.search(r"薪|工资|人工|员工|请几个人", previous_reply) and not explicit_orders:
            raise ValueError(
                "上一轮在问人工/工资，本轮没有明确销量单位；不能把300记为日均单量。请先确认它是否为每人每天的工资。"
            )
        if (
            not converting
            and re.search(r"每月|月均|一个月|一月|月销", user_text)
            and not re.search(r"每天|日均|一天", user_text)
        ):
            raise ValueError(
                "用户给的是月数量，请用 record_periodic_value 并确认营业天数，不能直接写日均单量。"
            )
    day_amount = any(
        re.search(r"每天|一天|日薪|日结|每日", clause) and not re.search(r"杯|单|卖|销售", clause)
        for clause in re.split(r"[，。；;\n]", user_text)
    )
    if day_amount:
        if any(
            key in changes
            for key in ("fixed_cost.staff", "fixed_cost.owner_salary", "fixed_cost.rent")
        ):
            raise ValueError(
                "日金额不能直接写入月成本。请用 record_periodic_value，先确认每月支付/工作天数；也可以等用户直接给出月金额。"
            )
    if "fixed_cost.rent" in changes and re.search(r"每年|一年|年租", user_text):
        raise ValueError("年租不能直接写月租，请用 record_periodic_value 按12个月换算。")


def monthly_amount(amount: float, period: str, days: float | None) -> float:
    value = Decimal(str(amount))
    if period == "day":
        if days is None:
            raise ValueError("请先向用户确认每月支付/工作天数，不能默认日薪乘30。")
        value *= Decimal(str(days))
    elif period == "year":
        value /= 12
    return float(value.quantize(Decimal("0.01")))


def daily_orders(amount: float, period: str, days: float | None) -> float:
    if period == "day":
        return amount
    if period != "month" or days is None:
        raise ValueError("月单量需先确认每月营业天数，年单量请先拆分月份。")
    return float(Decimal(str(amount)) / Decimal(str(days)))
