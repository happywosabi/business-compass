import pytest
from pytest import approx

from app.engine.inputs import build_inputs
from app.engine.params import MissingParametersError, PhysicalStoreParams


def test_startup_investment(milk_tea):
    inputs = build_inputs(milk_tea)
    assert inputs.deposit == approx(24000)
    assert inputs.renovation_rent == approx(12000)
    assert inputs.sunk_investment == approx(217000)
    assert inputs.recoverable_investment == approx(34000)
    assert inputs.startup_investment == approx(251000)


def test_rent_free_longer_than_renovation_means_no_renovation_rent(milk_tea):
    params = milk_tea.with_values({"startup.renovation_months": 2, "startup.rent_free_months": 3})
    assert build_inputs(params).renovation_rent == 0


def test_renovation_rent_after_rent_free_period(milk_tea):
    params = milk_tea.with_values({"startup.renovation_months": 3, "startup.rent_free_months": 1})
    assert build_inputs(params).renovation_rent == approx(24000)


def test_fee_rate_and_unit_margin(milk_tea):
    inputs = build_inputs(milk_tea)
    assert inputs.fee_rate == approx(0.08)
    assert inputs.unit_margin == approx(8.4)


def test_fee_rate_is_weighted_by_channel_share(milk_tea):
    params = milk_tea.with_values(
        {
            "revenue.channels": [
                {"name": "堂食", "share": 0.5, "fee_rate": 0},
                {"name": "外卖", "share": 0.5, "fee_rate": 0.2},
            ]
        }
    )
    # 0.5 × 0.2 + 0.006 + 0.02
    assert build_inputs(params).fee_rate == approx(0.126)


def test_staff_is_summed(milk_tea):
    params = milk_tea.with_values(
        {
            "fixed_cost.staff": [
                {"role": "店长", "count": 1, "monthly_cost": 7000},
                {"role": "店员", "count": 2, "monthly_cost": 5000},
            ]
        }
    )
    inputs = build_inputs(params)
    assert inputs.staff_count == 3
    assert inputs.staff_cost == approx(17000)


def test_fixed_cost(milk_tea):
    inputs = build_inputs(milk_tea)
    assert inputs.steady_fixed_cost() == approx(37000)
    assert inputs.steady_fixed_cost(include_owner=False) == approx(31000)


def test_rent_increases_every_year(milk_tea):
    params = milk_tea.with_values(
        {"fixed_cost.rent_increase_rate": 0.1, "fixed_cost.rent_increase_every_years": 1}
    )
    inputs = build_inputs(params)
    assert inputs.rent(1) == approx(12000)
    assert inputs.rent(12) == approx(12000)
    assert inputs.rent(13) == approx(13200)
    assert inputs.rent(25) == approx(14520)
    assert inputs.fixed_cost(13) == approx(37000 + 1200)


def test_rent_increases_every_two_years(milk_tea):
    params = milk_tea.with_values(
        {"fixed_cost.rent_increase_rate": 0.1, "fixed_cost.rent_increase_every_years": 2}
    )
    inputs = build_inputs(params)
    assert inputs.rent(24) == approx(12000)
    assert inputs.rent(25) == approx(13200)


def test_ramp_ends_at_one(milk_tea):
    inputs = build_inputs(milk_tea)
    assert [inputs.ramp_factor(t) for t in range(1, 7)] == [0.5, 0.65, 0.8, 0.9, 1.0, 1.0]


def test_seasonality_aligns_with_opening_month(milk_tea):
    july_high = [1.0] * 12
    july_high[6] = 1.5  # 7 月
    july_high[0] = 0.5  # 1 月（保持平均值为 1）
    params = milk_tea.with_values({"revenue.opening_month": 7, "revenue.seasonality": july_high})
    inputs = build_inputs(params)
    assert inputs.season_factor(1) == 1.5  # 开业第 1 个月是 7 月
    assert inputs.season_factor(7) == 0.5  # 第 7 个月是次年 1 月
    assert inputs.season_factor(13) == 1.5  # 第 13 个月又是 7 月


def test_scenarios_and_overrides(milk_tea):
    params = milk_tea.with_values(
        {
            "revenue.daily_orders": {"base": 200, "pessimistic": 150, "optimistic": 250},
            "fixed_cost.rent": {"base": 12000, "pessimistic": 13000},
        }
    )
    assert build_inputs(params, "pessimistic").daily_orders == 150
    assert build_inputs(params, "pessimistic").base_rent == 13000
    assert build_inputs(params, "optimistic").daily_orders == 250
    assert build_inputs(params, "optimistic").base_rent == 12000  # 乐观值为空，等于中性值

    only_orders = build_inputs(params, "base", {"revenue.daily_orders": "pessimistic"})
    assert only_orders.daily_orders == 150
    assert only_orders.base_rent == 12000


def test_unknown_override_key(milk_tea):
    with pytest.raises(KeyError):
        build_inputs(milk_tea, "base", {"revenue.not_a_param": "pessimistic"})


def test_missing_params_are_reported():
    with pytest.raises(MissingParametersError) as error:
        build_inputs(PhysicalStoreParams())
    assert "revenue.daily_orders" in error.value.keys


def test_capacity(milk_tea):
    assert build_inputs(milk_tea).capacity is None
    params = milk_tea.with_values(
        {"store.seats": 12, "store.turns_per_day": 3, "store.delivery_capacity": 50}
    )
    assert build_inputs(params).capacity == approx(86)
