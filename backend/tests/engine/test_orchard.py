from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.engine.orchard import OrchardParams, evaluate_orchard
from app.engine.params import MissingParametersError
from app.interview.orchard import Convert, convert


def orchard_data():
    def n(value):
        return {"base": value}

    return {
        "schema_version": 2,
        "orchard": {
            "period": n({"start": "2026-01-01", "end": "2026-12-31"}),
            "audience": n("wholesale"),
            "varieties": n(
                [
                    {
                        "id": "fruit-1",
                        "name": "蜜柚",
                        "harvest_kg": n(10000),
                        "loss_rate": n(0.1),
                        "grades": [
                            {
                                "id": "grade-1",
                                "name": "统货",
                                "share": 1,
                                "sell_through": n(0.8),
                                "channels": [
                                    {
                                        "id": "channel-1",
                                        "kind": "wholesale",
                                        "share": 1,
                                        "price": n(6),
                                        "packaging_per_kg": n(0),
                                        "logistics_per_kg": n(0),
                                        "fee_rate": n(0),
                                    }
                                ],
                            }
                        ],
                        "costs": {
                            "inputs": n(20000),
                            "irrigation": n(0),
                            "paid_labor": n(0),
                            "other": n(0),
                        },
                    }
                ]
            ),
            "shared_costs": n({"land_rent": n(10000), "maintenance": n(0), "other": n(0)}),
            "unpaid_labor": n(8000),
            "equipment": n(5000),
        },
    }


def test_fixed_acceptance_and_no_double_deductions():
    result = evaluate_orchard(OrchardParams.model_validate(orchard_data())).scenarios["base"]
    assert (
        result.revenue,
        result.operating_expense,
        result.operating_surplus,
        result.labor_adjusted_earnings,
    ) == (43200, 30000, 13200, 5200)
    assert result.varieties[0].saleable_kg == 9000
    assert result.varieties[0].sold_kg == 7200
    assert result.varieties[0].unsold_kg == 1800
    assert result.equipment_purchases == 5000
    assert result.break_even_price == pytest.approx(30000 / 7200)


def test_multiple_varieties_grades_and_channels():
    data = orchard_data()
    fruit = data["orchard"]["varieties"]["base"][0]
    grade = fruit["grades"][0]
    grade["share"] = 0.6
    other = deepcopy(grade)
    other.update(id="g2", share=0.4)
    grade["channels"][0]["share"] = 0.7
    retail = deepcopy(grade["channels"][0])
    retail.update(id="retail", kind="retail", share=0.3, price={"base": 10}, fee_rate={"base": 0.1})
    grade["channels"].append(retail)
    fruit["grades"].append(other)
    second = deepcopy(fruit)
    second.update(id="fruit-2", name="橙子")
    data["orchard"]["varieties"]["base"].append(second)
    result = evaluate_orchard(OrchardParams.model_validate(data)).scenarios["base"]
    assert result.sold_kg == 14400
    assert result.revenue == pytest.approx(96768)
    assert result.shared_cost == 10000
    assert result.operating_expense == pytest.approx(52592)
    assert result.labor_adjusted_earnings == pytest.approx(36176)


@pytest.mark.parametrize("key,value", [("harvest_kg", 0), ("loss_rate", 1)])
def test_zero_volume_no_break_even(key, value):
    data = orchard_data()
    data["orchard"]["varieties"]["base"][0][key] = {"base": value}
    result = evaluate_orchard(OrchardParams.model_validate(data)).scenarios["base"]
    assert result.revenue == 0
    assert result.break_even_price is None
    assert result.operating_surplus == -30000


def test_unknown_cost_is_not_zero_and_drafts_are_allowed():
    data = orchard_data()
    data["orchard"]["varieties"]["base"][0]["costs"]["paid_labor"] = None
    params = OrchardParams.model_validate(data)
    assert params.missing_keys() == ["orchard.varieties"]
    with pytest.raises(MissingParametersError):
        evaluate_orchard(params)
    assert len(OrchardParams().missing_keys()) == 5


def test_ratios_and_scenario_directions():
    data = orchard_data()
    fruit = data["orchard"]["varieties"]["base"][0]
    fruit["grades"][0]["share"] = 0.8
    with pytest.raises(ValidationError):
        OrchardParams.model_validate(data)
    fruit["grades"][0]["share"] = 1
    fruit["harvest_kg"]["pessimistic"] = 11000
    with pytest.raises(ValidationError):
        OrchardParams.model_validate(data)
    fruit["harvest_kg"].update(pessimistic=8000, optimistic=12000)
    result = evaluate_orchard(OrchardParams.model_validate(data))
    assert result.scenarios["pessimistic"].revenue == 34560
    assert result.scenarios["optimistic"].revenue == 51840
    assert result.sensitivity[0]["delta"] == -8640


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"kind": "weight", "amount": 5, "unit": "tonne"}, 5000),
        ({"kind": "price", "amount": 3, "unit": "jin"}, 6),
        ({"kind": "price", "amount": 30, "unit": "box", "net_kg": 5}, 6),
        ({"kind": "yield_per_mu", "amount": 2000, "unit": "jin", "area_mu": 10}, 10000),
        ({"kind": "labor", "amount": 300, "unit": "day", "days": 20, "people": 2}, 12000),
    ],
)
def test_conversions(body, expected):
    assert convert(Convert.model_validate(body))["value"] == expected


@pytest.mark.parametrize("kind,unit", [("price", "box"), ("yield_per_mu", "jin"), ("labor", "day")])
def test_ambiguous_units_require_context(kind, unit):
    with pytest.raises(ValueError):
        convert(Convert(kind=kind, unit=unit, amount=300))


def test_ai_update_requires_conversion_and_preserves_siblings():
    from app.interview.orchard import guard_orchard_changes, guard_orchard_update

    before = OrchardParams.model_validate(orchard_data())
    data = orchard_data()
    fruit = data["orchard"]["varieties"]["base"][0]
    fruit["harvest_kg"] = {"base": 5000, "note": "用户5吨换算为5000kg"}
    after = OrchardParams.model_validate(data)
    with pytest.raises(ValueError, match="先调用"):
        guard_orchard_update(before, after, "更正总采收5吨", [])
    guard_orchard_update(
        before, after, "更正总采收5吨", [convert(Convert(kind="weight", amount=5, unit="tonne"))]
    )
    with pytest.raises(ValueError, match="不得清空"):
        guard_orchard_changes({"orchard.varieties": None}, "两个人每天300，天数还没定")
    with pytest.raises(ValueError, match="ID"):
        guard_orchard_update(
            before, before.with_values({"orchard.varieties": []}), "我刚才说的数量是错的", []
        )


def test_identical_input_is_deterministic_and_equipment_unknown_stays_unknown():
    params = OrchardParams.model_validate(orchard_data()).with_values({"orchard.equipment": None})
    first, second = evaluate_orchard(params), evaluate_orchard(params)
    assert first == second
    assert first.scenarios["base"].equipment_purchases is None


def test_zero_sell_through_and_channel_fees_break_even():
    data = orchard_data()
    grade = data["orchard"]["varieties"]["base"][0]["grades"][0]
    grade["sell_through"]["base"] = 0
    result = evaluate_orchard(OrchardParams.model_validate(data)).scenarios["base"]
    assert result.sold_kg == 0 and result.break_even_price is None
    grade["sell_through"]["base"] = 0.8
    grade["channels"][0]["fee_rate"]["base"] = 0.1
    result = evaluate_orchard(OrchardParams.model_validate(data)).scenarios["base"]
    assert result.operating_expense == 34320
    assert result.break_even_price == pytest.approx(30000 / (7200 * 0.9))
