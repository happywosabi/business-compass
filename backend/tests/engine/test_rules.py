"""常识测试：参数往有利方向变化时，结果不应该变差。"""

import math

from app.engine.inputs import build_inputs
from app.engine.projection import project


def _payback(params) -> float:
    month = project(build_inputs(params)).payback_month
    return math.inf if month is None else month


def test_more_orders_never_delay_payback(milk_tea):
    paybacks = [
        _payback(milk_tea.with_values({"revenue.daily_orders": n})) for n in range(120, 401, 10)
    ]
    assert paybacks == sorted(paybacks, reverse=True)


def test_higher_rent_never_speeds_up_payback(milk_tea):
    paybacks = [
        _payback(milk_tea.with_values({"fixed_cost.rent": rent}))
        for rent in range(6000, 24001, 1000)
    ]
    assert paybacks == sorted(paybacks)


def test_higher_unit_cost_lowers_monthly_cash(milk_tea):
    cash = [
        build_inputs(milk_tea.with_values({"variable_cost.unit_cost": c})).steady_monthly_cash()
        for c in (3, 4, 5, 6, 7, 8)
    ]
    assert cash == sorted(cash, reverse=True)


def test_counting_owner_salary_never_speeds_up_payback(milk_tea):
    inputs = build_inputs(milk_tea)
    assert project(inputs).payback_month >= project(inputs, include_owner=False).payback_month
