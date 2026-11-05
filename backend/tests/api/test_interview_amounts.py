from uuid import uuid4

import pytest

from app.interview.amounts import daily_orders, guard_changes, monthly_amount

from .helpers import login, register
from .test_interview import FakeLLM, tool
from .test_profiles import create_profile

pytestmark = pytest.mark.anyio


def test_period_conversions_require_confirmed_days():
    assert monthly_amount(300, "day", 26) == 7800
    assert monthly_amount(54000, "year", None) == 4500
    assert monthly_amount(4500, "month", None) == 4500
    assert daily_orders(7800, "month", 26) == 300
    with pytest.raises(ValueError, match="确认"):
        monthly_amount(300, "day", None)
    with pytest.raises(ValueError, match="确认"):
        daily_orders(7800, "month", None)
    with pytest.raises(ValueError, match="人工/工资"):
        guard_changes(
            {"revenue.daily_orders": 300}, "两个人，每天300", "要请几个人、每人月薪多少？"
        )
    guard_changes({"revenue.daily_orders": 300}, "两个人，每天300单", "要请几个人、每人月薪多少？")


async def test_salary_context_rejects_sales_write_then_persists_exact_conversion(client, app, db):
    from sqlalchemy import update

    from app.db.base import utcnow
    from app.db.models import User

    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    profile = await create_profile(client)
    path = f"/api/profiles/{profile['id']}"
    app.state.llm = FakeLLM(
        [
            {
                "role": "assistant",
                "content": "租金4500已记下。还剩三笔大账：装修花多少？要请几个人、每人月薪多少？",
            },
            tool(
                "update_parameters",
                {"changes": {"revenue.daily_orders": 300}, "reason": "错误提取"},
            ),
            {
                "role": "assistant",
                "content": "300元是每人每天的工资吗？两人包含你自己吗？每月工作几天？",
            },
            tool(
                "record_periodic_value",
                {
                    "key": "fixed_cost.staff",
                    "amount": 300,
                    "period": "day",
                    "staff_count": 1,
                    "days_per_month": 26,
                    "staff_role": "亲属",
                    "reason": "用户确认亲戚日薪300，每月26天",
                },
            ),
            tool(
                "record_periodic_value",
                {
                    "key": "fixed_cost.owner_salary",
                    "amount": 5000,
                    "period": "month",
                    "reason": "老板每月5000",
                },
            ),
            {"role": "assistant", "content": "亲戚每月7800元，你自己的工资每月5000元已记下。"},
        ]
    )

    async def send(content):
        p = (await client.get(path)).json()
        return await client.post(
            path + "/interview/messages",
            json={
                "request_id": str(uuid4()),
                "revision": p["revision"],
                "content": content,
            },
        )

    await send("租金4500")
    response = await send("两个人，每天300")
    assert "event: done" in response.text
    params = (await client.get(path)).json()["parameters"]
    assert params["revenue"]["daily_orders"] is None

    assert params["fixed_cost"]["staff"] is None
    await send(
        "算我自己还有我亲戚，不另外请人了，就我们两个人干。亲戚每天300元、每月26天，我自己月薪5000。"
    )
    params = (await client.get(path)).json()["parameters"]
    assert params["fixed_cost"]["staff"]["base"] == [
        {"role": "亲属", "count": 1, "monthly_cost": 7800}
    ]
    assert "26天" in params["fixed_cost"]["staff"]["note"]
    assert params["fixed_cost"]["owner_salary"]["base"] == 5000
    assert params["revenue"]["daily_orders"] is None


@pytest.mark.parametrize("cleared", [None, {"base": None, "source": "user"}])
async def test_corrected_units_can_clear_old_order_count(client, app, db, cleared):
    from sqlalchemy import update

    from app.db.base import utcnow
    from app.db.models import User

    await register(client)
    await login(client)
    await db.execute(update(User).values(email_verified_at=utcnow()))
    await db.commit()
    profile = await create_profile(client, parameters={"revenue": {"daily_orders": {"base": 300}}})
    path = f"/api/profiles/{profile['id']}"
    app.state.llm = FakeLLM(
        [
            tool(
                "update_parameters",
                {"changes": {"revenue.daily_orders": cleared}, "reason": "金额不是数量，用户撤回"},
            ),
            {"role": "assistant", "content": "已清空原单量，等你确认再补。"},
        ]
    )
    response = await client.post(
        path + "/interview/messages",
        json={
            "request_id": str(uuid4()),
            "revision": 1,
            "content": "7800是每月销售额，不是7800杯，请先别估计单量",
        },
    )
    assert "event: done" in response.text
    assert (await client.get(path)).json()["parameters"]["revenue"]["daily_orders"] is None
