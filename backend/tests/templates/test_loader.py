from datetime import date

import pytest
from pytest import approx

from app.engine import PhysicalStoreParams, estimate_traffic, evaluate
from app.engine.params import ALL_KEYS, REQUIRED_KEYS
from app.templates import load_template

QUICK_KEYS = [
    "startup.renovation",
    "startup.equipment",
    "revenue.daily_orders",
    "revenue.avg_ticket",
    "fixed_cost.rent",
    "fixed_cost.staff",
    "fixed_cost.owner_salary",
]


@pytest.fixture
def template():
    return load_template("physical_store")


def _quick_params() -> PhysicalStoreParams:
    """只填了快速测算 7 项（加上业态共 8 项）的参数。"""
    return PhysicalStoreParams.model_validate(
        {
            "startup": {"renovation": {"base": 80000}, "equipment": {"base": 60000}},
            "revenue": {"daily_orders": {"base": 200}, "avg_ticket": {"base": 15}},
            "fixed_cost": {
                "rent": {"base": 12000},
                "staff": {"base": [{"role": "店员", "count": 3, "monthly_cost": 5000}]},
                "owner_salary": {"base": 6000},
            },
        }
    )


def test_every_param_has_a_spec(template):
    assert sorted(template.specs) == sorted(ALL_KEYS)


def test_quick_required_keys(template):
    assert sorted(template.quick_required_keys) == sorted(QUICK_KEYS)


def test_specs_with_a_stage_have_a_question(template):
    for spec in template.specs.values():
        if spec.stage != "none":
            assert spec.ask, f"{spec.key} 缺少问法"


@pytest.mark.parametrize("industry", load_template().industry_codes)
def test_every_required_param_is_asked_or_defaulted(template, industry):
    """每个测算必需参数，要么属于快速必填项（必须问），要么有默认值。"""
    config = template.industry(industry)
    defaulted = set(config.params) | set(config.derived) | {"revenue.opening_month"}
    uncovered = set(REQUIRED_KEYS) - defaulted - set(QUICK_KEYS)
    assert uncovered == set()


def test_quick_params_can_be_evaluated_after_filling_defaults(template):
    params = _quick_params()
    assert template.quick_missing(params) == []

    filled, keys = template.fill_defaults(params, "drinks", today=date(2026, 11, 4))
    assert filled.missing_keys() == []
    assert not set(keys) & set(QUICK_KEYS)
    assert sorted(filled.keys_by_source("default")) == sorted(keys)

    result = evaluate(filled, template.check_rules("drinks"))
    assert sorted(result.default_keys) == sorted(keys)
    assert result.scenarios["base"].payback_month is not None


def test_derived_unit_cost(template):
    filled, _ = template.fill_defaults(_quick_params(), "drinks")
    unit_cost = filled.get("variable_cost.unit_cost")
    assert unit_cost.base == approx(5.4)  # 15 元 × 36%
    assert unit_cost.source == "default"
    assert "客单价" in unit_cost.note


def test_derived_default_waits_for_its_reference(template):
    filled, keys = template.fill_defaults(PhysicalStoreParams(), "drinks")
    assert "variable_cost.unit_cost" not in keys  # 还没有客单价，无法推算


@pytest.mark.parametrize(("today", "month"), [(date(2026, 11, 4), 1), (date(2026, 3, 1), 5)])
def test_opening_month_is_two_months_later(template, today, month):
    filled, _ = template.fill_defaults(PhysicalStoreParams(), "drinks", today=today)
    assert filled.get("revenue.opening_month").base == month


def test_existing_values_are_not_overwritten(template, milk_tea):
    filled, keys = template.fill_defaults(milk_tea, "drinks")
    assert keys == []
    assert filled == milk_tea


def test_notes_explain_defaults(template):
    filled, _ = template.fill_defaults(_quick_params(), "drinks")
    assert "转让费" in filled.get("startup.transfer_fee").note
    assert filled.get("revenue.open_days").note  # 没有专门说明的也有通用说明


def test_unknown_industry(template):
    with pytest.raises(KeyError):
        template.fill_defaults(PhysicalStoreParams(), "spaceship")


def test_example_has_no_warnings_with_drinks_rules(template, milk_tea):
    result = evaluate(milk_tea, template.check_rules("drinks"))
    assert result.warnings == []


def test_traffic_defaults_work(template):
    estimate = estimate_traffic(
        "location", {"peak_hourly_passersby": 1000}, template.traffic_defaults("drinks")
    )
    assert estimate.base == approx(210)
