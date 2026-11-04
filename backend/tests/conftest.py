"""测试共用的示例数据。"""

import pytest

from app.engine.params import PhysicalStoreParams


def milk_tea_data() -> dict:
    """实体小店测算模型 第九节的奶茶店示例（数字为虚构）。

    比例费率 f = 0.3 × 0.18（外卖）+ 0.006（支付）+ 0.02（税费）= 0.08
    """
    return {
        "startup": {
            "transfer_fee": {"base": 50000},
            "renovation": {"base": 80000},
            "equipment": {"base": 60000},
            "licenses": {"base": 5000},
            "opening_marketing": {"base": 10000},
            "renovation_months": {"base": 1},
            "rent_free_months": {"base": 0},
            "deposit_months": {"base": 2},
            "initial_stock": {"base": 10000},
        },
        "revenue": {
            "daily_orders": {"base": 200},
            "avg_ticket": {"base": 15},
            "open_days": {"base": 30},
            "channels": {
                "base": [
                    {"name": "堂食", "share": 0.7, "fee_rate": 0},
                    {"name": "外卖", "share": 0.3, "fee_rate": 0.18},
                ]
            },
            "opening_month": {"base": 3},
            "ramp": {"base": [0.5, 0.65, 0.8, 0.9]},
            "seasonality": {"base": [1.0] * 12},
        },
        "variable_cost": {
            "unit_cost": {"base": 5.4},
            "payment_fee_rate": {"base": 0.006},
            "tax_rate": {"base": 0.02},
        },
        "fixed_cost": {
            "rent": {"base": 12000},
            "rent_increase_rate": {"base": 0},
            "rent_increase_every_years": {"base": 1},
            "staff": {"base": [{"role": "店员", "count": 3, "monthly_cost": 5000}]},
            "owner_salary": {"base": 6000},
            "utilities": {"base": 4000},
            "other_fixed": {"base": 0},
        },
        "store": {"lease_months": {"base": 36}},
    }


@pytest.fixture
def milk_tea() -> PhysicalStoreParams:
    return PhysicalStoreParams.model_validate(milk_tea_data())
