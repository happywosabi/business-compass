"""真实模型回归：仅使用虚构信息，创建独立临时用户，结束删除；不会发邮件。

从 backend 执行：uv run python -m scripts.evaluate_interview
输出只含指标，不含密钥或会话。
"""

import argparse
import asyncio
import json
from uuid import uuid4

from sqlalchemy import delete, select

from app.config import Settings
from app.db.base import utcnow
from app.db.models import AIRun, User
from app.interview.service import drive
from app.llm.runs import reserve
from app.main import create_app
from app.profiles.schemas import ProfileCreate
from app.profiles.service import create_profile, get_owned_profile

CASES = [
    ("精确客单", "我在杭州开奶茶店，平均每杯15元。", {"revenue.avg_ticket": 15}),
    ("模糊客单", "卖饮品的，客单价十几块。", {"revenue.avg_ticket": 15}),
    ("模糊装修", "奶茶店装修大概七八万。", {"startup.renovation": 75000}),
    ("模糊房租", "房租每个月一万出头。", {"fixed_cost.rent": 11000}),
    ("单量范围", "生意稳定后一天两三百杯。", {"revenue.daily_orders": 250}),
    (
        "一次多项",
        "房租12000元每月，设备6万元，装修8万元，客单价15元。",
        {
            "fixed_cost.rent": 12000,
            "startup.equipment": 60000,
            "startup.renovation": 80000,
            "revenue.avg_ticket": 15,
        },
    ),
    (
        "员工",
        "请3名店员，每个人月成本5000元含社保，老板工资按6000元。",
        {"fixed_cost.owner_salary": 6000},
    ),
    ("修正", "刚才房租说错了，以每月10000元为准。", {"fixed_cost.rent": 10000}),
    ("不知道", "我不知道日均单量，完全没调查过，不能乱填。", {"revenue.daily_orders": None}),
    ("默认确认", "每月营业天数我同意先用默认值。", {"revenue.open_days": 30}),
    ("负数", "房租是负的一万元，我随口乱说的，别记。", {"fixed_cost.rent": None}),
    (
        "客流产能",
        "先帮我按产能估算一下：12个座位，每天翻3次台，外卖每天最多100单。先别填日单量。",
        {"revenue.daily_orders": None},
    ),
]


async def main(multi=False):
    app = create_app(Settings())
    factory = app.state.session_factory
    user_id = None
    results = []
    try:
        async with factory() as db:
            user = User(
                email=f"ai-review-{uuid4().hex}@example.com",
                password_hash="disabled-review-account",
                email_verified_at=utcnow(),
                daily_ai_quota=100,
            )
            db.add(user)
            await db.commit()
            user_id = user.id
        cases = CASES if not multi else [(f"多轮-{i + 1}", "", {}) for i in range(10)]
        for index, (name, content, expected) in enumerate(cases):
            async with factory() as db:
                profile = await create_profile(db, user_id, ProfileCreate(name=name, city="杭州"))
                profile_id = profile.id
            messages = (
                [content]
                if not multi
                else [
                    "在杭州街边做饮品，主要卖给附近上班族。平均每杯15元。",
                    "房租每个月一万二，装修七八万，设备6万元。",
                    "请3名店员，每人月成本5000元含社保，老板工资按6000元。",
                    "客流没数过人，先别猜。我去看看同行再回来。"
                    if index % 2
                    else "营业天数我同意先按默认值，原料包装成本也同意先用默认估算。",
                    "我回来补充：稳定后一天两三百杯。房租刚才说错了，最后谈下来是每月10000元。",
                    "我确认目前的数字，先算一下，其余没有填写的测算参数同意用默认值。",
                ]
            )
            start = asyncio.get_running_loop().time()
            total_in, total_out, status = 0, 0, ""
            for turn, content in enumerate(messages):
                turns = turn + 1
                async with factory() as db:
                    profile = await get_owned_profile(db, user_id, profile_id)
                    user = await db.get(User, user_id)
                    run, _ = await reserve(
                        db,
                        user,
                        profile_id,
                        uuid4(),
                        "interview",
                        {"revision": profile.revision, "content": content},
                        app.state.settings,
                    )
                    run_id = run.id
                await drive(app, run_id)
                async with factory() as db:
                    run = await db.get(AIRun, run_id)
                    status = run.status
                    total_in += run.input_tokens
                    total_out += run.output_tokens
                if status == "cancelled":
                    raise asyncio.CancelledError()
                if status != "succeeded":
                    break
            async with factory() as db:
                profile = await get_owned_profile(db, user_id, profile_id)
                from app.engine import PhysicalStoreParams

                params = PhysicalStoreParams.model_validate(profile.parameters)
                if multi:
                    expected = {
                        "revenue.avg_ticket": 15,
                        "revenue.daily_orders": 250,
                        "fixed_cost.rent": 10000,
                        "startup.renovation": 75000,
                        "startup.equipment": 60000,
                        "fixed_cost.owner_salary": 6000,
                    }
                actual = {
                    key: params.get(key).base if params.get(key) else None for key in expected
                }
                if multi:
                    from app.db.models import Evaluation

                    snapshots = list(
                        await db.scalars(
                            select(Evaluation).where(Evaluation.profile_id == profile_id)
                        )
                    )
                ranges_ok = not multi or (
                    params.startup.renovation.pessimistic == 80000
                    and params.startup.renovation.optimistic == 70000
                )
                passed = (
                    ranges_ok
                    and actual == expected
                    and status == "succeeded"
                    and (not multi or bool(snapshots))
                )
                results.append(
                    {
                        "case": name,
                        "passed": passed,
                        "turns": turns,
                        "actual": actual,
                        "expected": expected,
                        "status": status,
                        "input_tokens": total_in,
                        "output_tokens": total_out,
                        "seconds": round(asyncio.get_running_loop().time() - start, 2),
                    }
                )
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        from pathlib import Path

        Path("../docs/访谈多轮回归结果.json" if multi else "../docs/访谈回归结果.json").write_text(
            json.dumps(
                {"model": app.state.settings.interview_model, "cases": results},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        if user_id:
            async with factory() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
        await app.state.ai_hub.close()
        await app.state.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--multi", action="store_true")
    asyncio.run(main(parser.parse_args().multi))
