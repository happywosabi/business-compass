import pytest

from app.engine.checks import CheckRules, run_checks
from app.engine.inputs import build_inputs

RULES = CheckRules(
    cost_ratio_min=0.25,
    cost_ratio_max=0.45,
    rent_ratio_max=0.20,
    labor_ratio_max=0.30,
    max_orders_per_staff_per_day=150,
    ramp_first_month_max=0.9,
    revenue_per_sqm_month_max=5000,
)


def _warnings(params, rules=RULES):
    return {c.rule for c in run_checks(build_inputs(params), rules) if c.level == "warning"}


def test_example_has_no_warnings(milk_tea):
    assert _warnings(milk_tea) == set()


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        ({"variable_cost.unit_cost": 20}, "unit_margin"),  # 成本高于售价
        ({"variable_cost.unit_cost": 2}, "cost_ratio"),  # 成本率 13%，偏低
        ({"variable_cost.unit_cost": 8}, "cost_ratio"),  # 成本率 53%，偏高
        ({"fixed_cost.rent": 30000}, "rent_ratio"),  # 房租占 33%
        (
            {"fixed_cost.staff": [{"role": "店员", "count": 6, "monthly_cost": 6000}]},
            "labor_ratio",  # 工资占 40%
        ),
        ({"fixed_cost.staff": []}, "orders_per_staff"),  # 只有老板一人，每天 200 单
        (
            {"store.seats": 10, "store.turns_per_day": 3, "store.delivery_capacity": 50},
            "capacity",  # 最多接待 80 单
        ),
        ({"revenue.ramp": [1.0]}, "ramp_first_month"),  # 开业第一个月就 100%
        ({"store.area_sqm": 10}, "revenue_per_sqm"),  # 每平米每月 9000 元
    ],
)
def test_each_rule_triggers(milk_tea, changes, rule):
    assert rule in _warnings(milk_tea.with_values(changes))


def test_no_hands_at_all(milk_tea):
    params = milk_tea.with_values({"fixed_cost.staff": [], "fixed_cost.owner_salary": 0})
    assert "orders_per_staff" in _warnings(params)


def test_rules_without_thresholds_are_skipped(milk_tea):
    rules = {c.rule for c in run_checks(build_inputs(milk_tea), CheckRules())}
    # 不需要阈值的检查仍会运行；没有座位数据时跳过接待能力检查
    assert rules == {"unit_margin"}


def test_info_results_carry_values(milk_tea):
    results = {c.rule: c for c in run_checks(build_inputs(milk_tea), RULES)}
    assert results["rent_ratio"].level == "info"
    assert results["rent_ratio"].value == pytest.approx(12000 / 90000)
    assert "13%" in results["rent_ratio"].message
