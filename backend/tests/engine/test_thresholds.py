import pytest
from pytest import approx

from app.engine.inputs import build_inputs
from app.engine.thresholds import compute_thresholds

KEYS = ["revenue.daily_orders", "revenue.avg_ticket", "variable_cost.unit_cost", "fixed_cost.rent"]


@pytest.mark.parametrize("key", KEYS)
def test_threshold_plugged_back_gives_zero_cash(milk_tea, key):
    """自我核对：把临界值代回模型，稳定期月现金流应正好为 0。"""
    thresholds, _ = compute_thresholds(build_inputs(milk_tea))
    at_threshold = milk_tea.with_values({key: thresholds[key].value})
    assert build_inputs(at_threshold).steady_monthly_cash() == approx(0, abs=1e-6)


def test_no_break_even_when_every_order_loses_money(milk_tea):
    # 每单成本 20 元 > 售价，每单毛利为负
    thresholds, safety_margin = compute_thresholds(
        build_inputs(milk_tea.with_values({"variable_cost.unit_cost": 20}))
    )
    assert thresholds["revenue.daily_orders"].value is None
    assert thresholds["revenue.daily_orders"].headroom is None
    assert safety_margin is None
    # 临界按单成本仍然存在（7.63 元），只是当前成本已远高于它
    assert thresholds["variable_cost.unit_cost"].value == approx(7.633, abs=0.001)
    assert thresholds["variable_cost.unit_cost"].headroom < 0


def test_no_rent_threshold_when_even_free_rent_loses(milk_tea):
    # 一天只卖 10 单：房租为 0 也亏
    thresholds, _ = compute_thresholds(
        build_inputs(milk_tea.with_values({"revenue.daily_orders": 10}))
    )
    assert thresholds["fixed_cost.rent"].value is None


def test_headroom_is_positive_when_already_losing(milk_tea):
    # 一天卖 100 单（保本要 147 单），余量为正：还需要增加 47%
    thresholds, safety_margin = compute_thresholds(
        build_inputs(milk_tea.with_values({"revenue.daily_orders": 100}))
    )
    assert thresholds["revenue.daily_orders"].headroom > 0
    assert safety_margin < 0


def test_zero_rent_has_no_headroom(milk_tea):
    thresholds, _ = compute_thresholds(build_inputs(milk_tea.with_values({"fixed_cost.rent": 0})))
    assert thresholds["fixed_cost.rent"].value is not None
    assert thresholds["fixed_cost.rent"].headroom is None
