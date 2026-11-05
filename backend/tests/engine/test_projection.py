from pytest import approx

from app.engine.inputs import build_inputs
from app.engine.projection import MAX_MONTHS, project


def test_projects_120_months(milk_tea):
    projection = project(build_inputs(milk_tea))
    assert len(projection.months) == MAX_MONTHS
    assert projection.months[-1].t == MAX_MONTHS


def test_never_pays_back(milk_tea):
    projection = project(build_inputs(milk_tea.with_values({"fixed_cost.rent": 60000})))
    assert projection.payback_month is None
    assert projection.first_profitable_month is None
    # 一直亏钱，最低点出现在最后一个月
    assert projection.cash_low_month == MAX_MONTHS


def test_profitable_from_first_month_without_ramp(milk_tea):
    projection = project(build_inputs(milk_tea.with_values({"revenue.ramp": []})))
    assert projection.first_profitable_month == 1
    assert projection.months[0].cash_flow == approx(13400)
    # 开业后现金一直上升，最低点就是开业前
    assert projection.cash_low_month == 0


def test_seasonality_shifts_monthly_orders(milk_tea):
    july_high = [1.0] * 12
    july_high[6] = 1.5
    july_high[0] = 0.5
    params = milk_tea.with_values({"revenue.opening_month": 7, "revenue.seasonality": july_high})
    projection = project(build_inputs(params))
    assert projection.months[0].daily_orders == approx(200 * 0.5 * 1.5)  # 7 月，爬坡 50%
    assert projection.months[6].daily_orders == approx(200 * 1.0 * 0.5)  # 次年 1 月


def test_revenue_column(milk_tea):
    projection = project(build_inputs(milk_tea))
    # 第 5 个月：200 单 × 30 天 × 15 元
    assert projection.months[4].revenue == approx(90000)


def test_rent_increase_slows_payback(milk_tea):
    flat = project(build_inputs(milk_tea))
    rising = project(
        build_inputs(
            milk_tea.with_values(
                {"fixed_cost.rent_increase_rate": 0.1, "fixed_cost.rent_increase_every_years": 1}
            )
        )
    )
    # 前 12 个月相同，第 13 个月起多付房租
    assert rising.months[11].cash == approx(flat.months[11].cash)
    assert rising.months[12].cash_flow == approx(flat.months[12].cash_flow - 1200)
    assert rising.payback_month >= flat.payback_month


def test_short_months_argument(milk_tea):
    projection = project(build_inputs(milk_tea), months=12)
    assert len(projection.months) == 12
    assert projection.payback_month is None  # 12 个月内回不了本


def test_funding_uses_36_month_window_but_payback_checks_120(milk_tea):
    from app.engine import evaluate

    params = milk_tea.with_values({"fixed_cost.rent_increase_rate": 0.5})
    full = project(build_inputs(params))
    result = evaluate(params).scenarios["base"]
    assert full.cash_low_month > 36
    assert result.cash_low.month <= 36
    assert result.cash_low.amount == min(row.cash for row in result.monthly)
    assert result.payback_month == full.payback_month
