import pytest
from pydantic import ValidationError
from pytest import approx

from app.engine.results import TierValues
from app.engine.traffic import TrafficDefaults, estimate_traffic

DEFAULTS = TrafficDefaults(
    entry_rate=TierValues(pessimistic=0.03, base=0.05, optimistic=0.08),
    conversion_rate=TierValues(pessimistic=0.6, base=0.7, optimistic=0.8),
    day_factor=TierValues(pessimistic=5, base=6, optimistic=7),
    delivery_share=TierValues(pessimistic=0.5, base=0.4, optimistic=0.3),
)


def test_location_with_defaults():
    estimate = estimate_traffic("location", {"peak_hourly_passersby": 1000}, DEFAULTS)
    assert estimate.pessimistic == approx(1000 * 0.03 * 0.6 * 5)  # 90
    assert estimate.base == approx(1000 * 0.05 * 0.7 * 6)  # 210
    assert estimate.optimistic == approx(1000 * 0.08 * 0.8 * 7)  # 448
    assert estimate.used_defaults == ["entry_rate", "conversion_rate", "day_factor"]


def test_location_with_user_values():
    estimate = estimate_traffic(
        "location", {"peak_hourly_passersby": 1000, "entry_rate": 0.1}, DEFAULTS
    )
    assert estimate.pessimistic == approx(1000 * 0.1 * 0.6 * 5)
    assert estimate.base == approx(1000 * 0.1 * 0.7 * 6)
    assert "entry_rate" not in estimate.used_defaults


def test_benchmark_with_two_stores():
    estimate = estimate_traffic(
        "benchmark",
        {"stores": [{"monthly_delivery_sales": 4500}, {"monthly_delivery_sales": 6000}]},
        DEFAULTS,
    )
    # 每天外卖 150 单、200 单
    assert estimate.pessimistic == approx(150 / 0.5)  # 两家中较低的，按外卖占比高估算
    assert estimate.base == approx((150 / 0.4 + 200 / 0.4) / 2)  # 中位数
    assert estimate.optimistic == approx(200 / 0.3)  # 两家中较高的，按外卖占比低估算


def test_benchmark_with_known_delivery_share():
    estimate = estimate_traffic(
        "benchmark", {"stores": [{"monthly_delivery_sales": 4500, "delivery_share": 0.5}]}, DEFAULTS
    )
    assert estimate.pessimistic == estimate.base == estimate.optimistic == approx(300)
    assert estimate.used_defaults == []


def test_capacity_is_an_upper_bound():
    estimate = estimate_traffic(
        "capacity", {"seats": 12, "turns_per_day": 3, "delivery_capacity": 50}, DEFAULTS
    )
    assert estimate.base == approx(86)
    assert estimate.is_upper_bound


def test_unknown_method():
    with pytest.raises(ValueError):
        estimate_traffic("guess", {}, DEFAULTS)


def test_invalid_inputs():
    with pytest.raises(ValidationError):
        estimate_traffic("location", {"peak_hourly_passersby": -1}, DEFAULTS)
    with pytest.raises(ValidationError):
        estimate_traffic("benchmark", {"stores": []}, DEFAULTS)
