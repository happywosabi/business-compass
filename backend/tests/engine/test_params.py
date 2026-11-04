import pytest
from pydantic import ValidationError

from app.engine.params import (
    ALL_KEYS,
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    ParamValue,
    PhysicalStoreParams,
)
from tests.conftest import milk_tea_data


def test_example_is_valid_and_complete(milk_tea):
    assert milk_tea.missing_keys() == []


def test_empty_params_miss_all_required_keys():
    params = PhysicalStoreParams()
    assert params.missing_keys() == list(REQUIRED_KEYS)
    assert not set(params.missing_keys()) & OPTIONAL_KEYS


def test_key_list_matches_document():
    # 数据结构文档 6.2：启动 9 + 收入 7 + 变动成本 3 + 固定成本 7 + 门店 6 = 32，其中 5 个可选
    assert len(ALL_KEYS) == 32
    assert len(REQUIRED_KEYS) == 27


def test_missing_optimistic_and_pessimistic_fall_back_to_base():
    value = ParamValue[float](base=200)
    assert value.get("pessimistic") == 200
    assert value.get("base") == 200
    assert value.get("optimistic") == 200
    assert not value.has_range


def test_three_tiers():
    value = ParamValue[float](base=200, pessimistic=150, optimistic=250)
    assert value.get("pessimistic") == 150
    assert value.get("optimistic") == 250
    assert value.has_range


def test_range_equal_to_base_is_not_a_range():
    assert not ParamValue[float](base=200, pessimistic=200).has_range


def test_get_by_key(milk_tea):
    assert milk_tea.get("revenue.daily_orders").base == 200
    with pytest.raises(KeyError):
        milk_tea.get("revenue.not_a_param")


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("variable_cost.payment_fee_rate", 1.5),  # 比例超过 1
        ("variable_cost.tax_rate", -0.1),  # 比例为负
        ("fixed_cost.rent", -1),  # 金额为负
        ("revenue.avg_ticket", 0),  # 客单价必须大于 0
        ("revenue.daily_orders", 0),  # 日单量必须大于 0
        ("revenue.opening_month", 13),  # 月份超出 1–12
        ("revenue.open_days", 32),  # 一个月最多 31 天
        ("store.lease_months", 0),  # 租约至少 1 个月
    ],
)
def test_hard_constraints(milk_tea, key, bad_value):
    with pytest.raises(ValidationError):
        milk_tea.with_values({key: bad_value})


def test_pessimistic_value_is_also_validated(milk_tea):
    with pytest.raises(ValidationError):
        milk_tea.with_values({"fixed_cost.rent": {"base": 12000, "pessimistic": -5}})


def test_channel_shares_must_sum_to_one(milk_tea):
    bad = [
        {"name": "堂食", "share": 0.7, "fee_rate": 0},
        {"name": "外卖", "share": 0.2, "fee_rate": 0.18},
    ]
    with pytest.raises(ValidationError, match="占比之和"):
        milk_tea.with_values({"revenue.channels": bad})


def test_empty_channel_list_is_allowed(milk_tea):
    assert milk_tea.with_values({"revenue.channels": []}).get("revenue.channels").base == []


def test_seasonality_needs_12_values(milk_tea):
    with pytest.raises(ValidationError, match="12 个"):
        milk_tea.with_values({"revenue.seasonality": [1.0] * 11})


def test_seasonality_mean_must_be_one(milk_tea):
    with pytest.raises(ValidationError, match="平均值"):
        milk_tea.with_values({"revenue.seasonality": [1.2] * 12})


def test_unknown_fields_are_rejected():
    data = milk_tea_data()
    data["revenue"]["foo"] = {"base": 1}
    with pytest.raises(ValidationError):
        PhysicalStoreParams.model_validate(data)


def test_unknown_source_is_rejected(milk_tea):
    with pytest.raises(ValidationError):
        milk_tea.with_values({"fixed_cost.rent": {"base": 12000, "source": "guess"}})


def test_with_values_accepts_plain_values_and_param_values(milk_tea):
    changed = milk_tea.with_values(
        {
            "revenue.daily_orders": 180,
            "fixed_cost.rent": ParamValue[float](base=11000, source="ai_inferred"),
            "variable_cost.unit_cost": {"base": 6, "pessimistic": 7},
        }
    )
    assert changed.get("revenue.daily_orders").base == 180
    assert changed.get("fixed_cost.rent").source == "ai_inferred"
    assert changed.get("variable_cost.unit_cost").get("pessimistic") == 7
    # 原参数不变
    assert milk_tea.get("revenue.daily_orders").base == 200


def test_with_values_none_clears_a_param(milk_tea):
    assert milk_tea.with_values({"fixed_cost.rent": None}).missing_keys() == ["fixed_cost.rent"]


def test_with_values_rejects_unknown_key(milk_tea):
    with pytest.raises(KeyError):
        milk_tea.with_values({"revenue.not_a_param": 1})


def test_keys_by_source(milk_tea):
    changed = milk_tea.with_values({"variable_cost.tax_rate": {"base": 0.02, "source": "default"}})
    assert changed.keys_by_source("default") == ["variable_cost.tax_rate"]


def test_json_round_trip(milk_tea):
    data = milk_tea.model_dump(mode="json")
    assert PhysicalStoreParams.model_validate(data) == milk_tea
