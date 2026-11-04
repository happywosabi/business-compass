"""实体小店测算模型 第九节：奶茶店示例。所有数字必须与文档一致。"""

import math

from pytest import approx

from app.engine import ENGINE_VERSION, evaluate, what_if
from app.engine.inputs import build_inputs
from app.engine.projection import project

MONEY = 0.01  # 金额允许 0.01 元误差


# ---- 9.3 逐月现金（含老板工资）----


def test_monthly_cash(milk_tea):
    projection = project(build_inputs(milk_tea))
    assert projection.cash_at(0) == approx(-251000, abs=MONEY)

    expected = [
        # (月份, 当月现金流, 月末现金)
        (1, -11800, -262800),
        (2, -4240, -267040),
        (3, 3320, -263720),
        (4, 8360, -255360),
        (5, 13400, -241960),
    ]
    for t, cash_flow, cash in expected:
        month = projection.months[t - 1]
        assert month.t == t
        assert month.cash_flow == approx(cash_flow, abs=MONEY)
        assert month.cash == approx(cash, abs=MONEY)


# ---- 9.2 预期输出中与现金曲线相关的部分 ----


def test_cash_curve_outputs(milk_tea):
    inputs = build_inputs(milk_tea)
    with_owner = project(inputs)
    without_owner = project(inputs, include_owner=False)

    assert inputs.steady_monthly_cash() == approx(13400, abs=MONEY)
    assert inputs.steady_monthly_cash(include_owner=False) == approx(19400, abs=MONEY)

    assert with_owner.first_profitable_month == 3
    assert without_owner.first_profitable_month == 2

    assert with_owner.cash_low_amount == approx(-267040, abs=MONEY)
    assert with_owner.cash_low_month == 2

    assert with_owner.payback_month == 21
    assert without_owner.payback_month == 15


# ---- 9.4 客流比预期少 20% ----


def test_twenty_percent_less_traffic(milk_tea):
    inputs = build_inputs(milk_tea.with_values({"revenue.daily_orders": 160}))
    projection = project(inputs)

    assert inputs.steady_monthly_cash() == approx(3320, abs=MONEY)
    assert projection.cash_low_amount == approx(-284088, abs=MONEY)
    assert projection.cash_low_month == 4
    assert projection.payback_month == 80
    assert projection.payback_month > inputs.lease_months  # 租约检查：红灯


def test_break_even_orders_rounds_up_for_display(milk_tea):
    inputs = build_inputs(milk_tea)
    break_even = inputs.steady_fixed_cost() / (inputs.unit_margin * inputs.open_days)
    assert break_even == approx(146.83, abs=0.01)
    assert math.ceil(break_even) == 147


# ---- 9.2 预期输出：通过总入口 evaluate 完整核对 ----


def test_full_evaluation(milk_tea):
    result = evaluate(milk_tea)
    assert result.engine_version == ENGINE_VERSION
    base = result.scenarios["base"]

    assert base.unit_margin == approx(8.4)
    assert base.fee_rate == approx(0.08)
    assert base.startup.sunk == approx(217000, abs=MONEY)
    assert base.startup.recoverable == approx(34000, abs=MONEY)
    assert base.startup.total == approx(251000, abs=MONEY)
    assert base.steady_monthly_revenue == approx(90000, abs=MONEY)
    assert base.steady_fixed_cost == approx(37000, abs=MONEY)
    assert base.steady_monthly_cash == approx(13400, abs=MONEY)
    assert base.steady_monthly_cash_excl_owner == approx(19400, abs=MONEY)
    assert base.first_profitable_month == 3
    assert base.first_profitable_month_excl_owner == 2
    assert base.cash_low.amount == approx(-267040, abs=MONEY)
    assert base.cash_low.month == 2
    assert base.suggested_funding == [approx(341040, abs=MONEY), approx(378040, abs=MONEY)]
    assert base.payback_month == 21
    assert base.payback_month_excl_owner == 15
    assert base.lease_check == "pass"

    # 逐月数据：第 0 … 36 个月
    assert len(base.monthly) == 37
    assert base.monthly[0].t == 0
    assert base.monthly[0].cash_flow is None
    assert base.monthly[2].cash == approx(-267040, abs=MONEY)


def test_thresholds_and_safety_margin(milk_tea):
    result = evaluate(milk_tea)
    t = result.thresholds

    assert t["revenue.daily_orders"].value == approx(146.83, abs=0.01)
    assert t["revenue.avg_ticket"].value == approx(12.57, abs=0.01)
    assert t["variable_cost.unit_cost"].value == approx(7.63, abs=0.01)
    assert t["fixed_cost.rent"].value == approx(25400, abs=MONEY)

    assert t["revenue.daily_orders"].headroom == approx(-0.266, abs=0.001)
    assert t["revenue.avg_ticket"].headroom == approx(-0.162, abs=0.001)
    assert t["variable_cost.unit_cost"].headroom == approx(0.414, abs=0.001)
    assert t["fixed_cost.rent"].headroom == approx(1.117, abs=0.001)

    assert result.safety_margin == approx(0.266, abs=0.001)


def test_three_scenarios_match_section_9_4(milk_tea):
    """悲观情景填"客流少 20%"，结果应与 9.4 一致。"""
    params = milk_tea.with_values({"revenue.daily_orders": {"base": 200, "pessimistic": 160}})
    result = evaluate(params)
    pessimistic = result.scenarios["pessimistic"]

    assert pessimistic.steady_monthly_cash == approx(3320, abs=MONEY)
    assert pessimistic.cash_low.amount == approx(-284088, abs=MONEY)
    assert pessimistic.cash_low.month == 4
    assert pessimistic.payback_month == 80
    assert pessimistic.lease_check == "fail"
    # 乐观值为空，等于中性
    assert result.scenarios["optimistic"].payback_month == 21


def test_result_can_be_saved_as_json(milk_tea):
    data = evaluate(milk_tea).model_dump(mode="json")
    assert data["scenarios"]["base"]["payback_month"] == 21
    assert set(data["scenarios"]) == {"pessimistic", "base", "optimistic"}


def test_what_if_lower_rent(milk_tea):
    result = what_if(milk_tea, {"fixed_cost.rent": 10000})
    assert result.changed_keys == ["fixed_cost.rent"]
    assert result.before.steady_monthly_cash == approx(13400, abs=MONEY)
    assert result.after.steady_monthly_cash == approx(15400, abs=MONEY)
    assert result.after.payback_month < result.before.payback_month
    # 原参数不变
    assert milk_tea.get("fixed_cost.rent").base == 12000
