from pytest import approx

from app.engine import evaluate
from app.engine.inputs import build_inputs
from app.engine.projection import project
from app.engine.sensitivity import run_sensitivity


def _with_ranges(milk_tea):
    # 三个参数各自向不利方向变化 10% 左右
    return milk_tea.with_values(
        {
            "revenue.avg_ticket": {"base": 15, "pessimistic": 13.5, "optimistic": 16.5},
            "revenue.daily_orders": {"base": 200, "pessimistic": 180, "optimistic": 220},
            "fixed_cost.rent": {"base": 12000, "pessimistic": 13000, "optimistic": 11000},
        }
    )


def test_ranking(milk_tea):
    items = run_sensitivity(_with_ranges(milk_tea))
    # 客单价降 10% 每单少赚 1.38 元，比单量降 10% 更伤；房租多 1000 元影响最小
    assert [i.key for i in items] == [
        "revenue.avg_ticket",
        "revenue.daily_orders",
        "fixed_cost.rent",
    ]


def test_only_params_with_ranges_are_included(milk_tea):
    assert run_sensitivity(milk_tea) == []
    assert len(run_sensitivity(_with_ranges(milk_tea))) == 3


def test_values_are_consistent_with_projection(milk_tea):
    params = _with_ranges(milk_tea)
    item = next(i for i in run_sensitivity(params) if i.key == "revenue.daily_orders")
    base_cash = project(build_inputs(params)).cash_at(36)
    pessimistic_cash = project(
        build_inputs(params, "base", {"revenue.daily_orders": "pessimistic"})
    ).cash_at(36)

    assert item.cash_at_month_36.base == approx(base_cash)
    assert item.cash_at_month_36.pessimistic == approx(pessimistic_cash)
    assert item.downside == approx(base_cash - pessimistic_cash)
    assert item.downside > 0
    assert item.swing > item.downside
    assert item.payback_month.base == 21
    assert item.payback_month.pessimistic > 21
    assert item.payback_month.optimistic < 21


def test_startup_cost_is_ranked_even_though_monthly_cash_is_unchanged(milk_tea):
    """装修超支不影响每月现金流，但会影响第 36 个月末的钱，所以也能排进来。"""
    params = milk_tea.with_values({"startup.renovation": {"base": 80000, "pessimistic": 120000}})
    (item,) = run_sensitivity(params)
    assert item.key == "startup.renovation"
    assert item.downside == approx(40000)


def test_evaluate_includes_sensitivity(milk_tea):
    result = evaluate(_with_ranges(milk_tea))
    assert result.sensitivity[0].key == "revenue.avg_ticket"
