from datetime import date

import pytest
from pydantic import ValidationError

from app.engine.fruit_retail import FruitRetailParams, evaluate_fruit, fruit_what_if


def fruit_data(stage="preparing"):
    values = dict(
        revenue_basis="revenue",
        sales_amount=90000,
        sales_period="month",
        open_days=30,
        cost_basis="margin_loss",
        gross_margin=0.3,
        loss_rate=0.1,
        packaging_rate=0.01,
        channel_rate=0.02,
        payment_tax_rate=0,
        rent=4500,
        staff_cost=6000,
        owner_salary=5000,
        utilities=1500,
        delivery_fixed=0,
        other_fixed=0,
        renovation=30000,
        equipment=20000,
        deposit=9000,
        stock=4000,
        stocking_days=3,
    )
    return {
        "schema_version": 3,
        "stage": stage,
        "forecast_start": "2026-11-06",
        "fruit": {k: {"base": v} for k, v in values.items()},
    }


def test_equivalent_cost_bases_stock_and_no_double_counting():
    p = FruitRetailParams.model_validate(fruit_data())
    a = evaluate_fruit(p).scenarios["base"]
    assert a.monthly_procurement == pytest.approx(70000)
    assert a.reference_stock == pytest.approx(7000)
    assert a.stock_shortfall == pytest.approx(3000)
    assert a.startup_investment == 63000
    assert a.funding_required == pytest.approx(66000)
    assert a.monthly_net == pytest.approx(300)
    assert a.monthly_net_excl_owner == pytest.approx(5300)
    equivalent = p.with_values(
        {
            "fruit.cost_basis": "inclusive",
            "fruit.procurement_ratio": 7 / 9,
            "fruit.gross_margin": None,
            "fruit.loss_rate": None,
        }
    )
    b = evaluate_fruit(equivalent).scenarios["base"]
    for key in (
        "monthly_procurement",
        "monthly_net",
        "reference_stock",
        "stock_shortfall",
        "funding_required",
        "break_even_daily",
    ):
        assert getattr(b, key) == pytest.approx(getattr(a, key))
    assert "fruit.loss_rate" not in equivalent.required_keys()
    with pytest.raises(ValidationError, match="互斥"):
        equivalent.with_values({"fruit.loss_rate": 0.1})


def test_day_month_and_transactions_equivalence():
    p = FruitRetailParams.model_validate(fruit_data())
    monthly = evaluate_fruit(p).scenarios["base"]
    daily = p.with_values({"fruit.sales_amount": 3000, "fruit.sales_period": "day"})
    assert evaluate_fruit(daily).scenarios["base"] == monthly
    transactions = p.with_values(
        {
            "fruit.revenue_basis": "transactions",
            "fruit.sales_amount": None,
            "fruit.sales_period": None,
            "fruit.daily_transactions": 100,
            "fruit.avg_ticket": 30,
        }
    )
    assert evaluate_fruit(transactions).scenarios["base"] == monthly
    with pytest.raises(ValidationError, match="互斥"):
        transactions.with_values({"fruit.sales_amount": 3000})


def test_operating_ignores_sunk_cost_and_excess_stock_unknown_cash():
    p = FruitRetailParams.model_validate(fruit_data("operating"))
    p = p.with_values({"fruit.stock": 10000})
    base = evaluate_fruit(p).scenarios["base"]
    assert base.startup_investment is None
    assert base.funding_required == base.stock_shortfall == 0
    assert base.payback_month is None
    assert base.cash_shortfall is base.runway_months is None
    assert base.monthly[0].cash == 0
    assert base.monthly[-1].cash == pytest.approx(base.monthly_net * 36)
    assert (
        evaluate_fruit(
            p.with_values(
                {"fruit.renovation": None, "fruit.equipment": None, "fruit.deposit": None}
            )
        ).scenarios["base"]
        == base
    )
    assert evaluate_fruit(p).forecast_start == date(2026, 11, 6)


def test_known_cash_shortfall_and_runway_do_not_liquidate_excess_stock():
    p = FruitRetailParams.model_validate(fruit_data("operating"))
    p = p.with_values(
        {"fruit.sales_amount": 0, "fruit.stock": 100000, "fruit.available_cash": 34000}
    )
    base = evaluate_fruit(p).scenarios["base"]
    assert base.monthly_net == -17000
    assert base.runway_months == 2
    assert base.reference_stock == 0
    assert base.cash_shortfall == 0
    p = p.with_values({"fruit.sales_amount": 90000, "fruit.stock": 0, "fruit.available_cash": 5000})
    assert evaluate_fruit(p).scenarios["base"].cash_shortfall == pytest.approx(2000)


@pytest.mark.parametrize(
    "key,value",
    [
        ("loss_rate", 1),
        ("sales_amount", -1),
        ("gross_margin", 1.01),
        ("open_days", 0),
        ("rent", float("inf")),
    ],
)
def test_invalid_inputs(key, value):
    p = FruitRetailParams.model_validate(fruit_data())
    with pytest.raises(ValidationError):
        p.with_values({f"fruit.{key}": value})


def test_zero_loss_negative_margin_and_no_finite_break_even():
    p = FruitRetailParams.model_validate(fruit_data())
    p = p.with_values({"fruit.loss_rate": 0})
    assert evaluate_fruit(p).scenarios["base"].monthly_procurement == pytest.approx(63000)
    p = p.with_values(
        {
            "fruit.cost_basis": "inclusive",
            "fruit.gross_margin": None,
            "fruit.loss_rate": None,
            "fruit.procurement_ratio": 1.2,
        }
    )
    base = evaluate_fruit(p).scenarios["base"]
    assert base.monthly_net < 0
    assert base.break_even_daily is base.break_even_monthly is base.payback_month is None


def test_scenario_direction_sensitivity_and_preview_is_pure():
    p = FruitRetailParams.model_validate(fruit_data())
    p = p.with_values(
        {
            "fruit.sales_amount": {"base": 90000, "pessimistic": 80000, "optimistic": 100000},
            "fruit.loss_rate": {"base": 0.1, "pessimistic": 0.15, "optimistic": 0.05},
        }
    )
    before = p.model_dump()
    result = evaluate_fruit(p)
    assert (
        result.scenarios["pessimistic"].monthly_net
        < result.scenarios["base"].monthly_net
        < result.scenarios["optimistic"].monthly_net
    )
    assert len(result.sensitivity) == 4
    trial = fruit_what_if(p, {"fruit.rent": 3500})
    assert trial.surplus_delta == pytest.approx(1000)
    assert p.model_dump() == before
    with pytest.raises(ValidationError, match="方向"):
        p.with_values({"fruit.gross_margin": {"base": 0.3, "pessimistic": 0.4}})
