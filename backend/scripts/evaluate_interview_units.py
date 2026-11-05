"""真实模型单位回归，使用独立临时账号；不发送邮件，结束时删除测试数据。"""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

from app.config import Settings
from app.db.base import utcnow
from app.db.models import AIRun, Conversation, Message, User
from app.interview.service import PROMPT_VERSION, drive
from app.llm.runs import reserve
from app.main import create_app
from app.profiles.schemas import ProfileCreate
from app.profiles.service import create_profile, get_owned_profile

CASES = [
    (
        "工资上下文与亲属劳动",
        "租金4500已记下。还剩三笔大账：装修花多少？要请几个人、每人月薪多少？",
        [
            ("两个人，每天300", {"sales": None, "staff": None}),
            ("算我自己还有我亲戚，不另外请人了，就我们两个人干", {"sales": None, "staff": None}),
            (
                "明确一下，亲戚每人每天300元，每个月工作26天；我自己的工资按每月5000元。",
                {"sales": None, "staff": 7800, "owner": 5000},
            ),
        ],
    ),
    (
        "年租月租改口",
        "房租多少钱？可以给月租或年租。",
        [
            ("房租每年54000元。", {"rent": 4500}),
            ("刚才说错了，最终签约是每月6000元。", {"rent": 6000}),
        ],
    ),
    (
        "月订单与月销售额",
        "日均单量大概多少？如果只知道月单量，请告诉我每月营业天数。",
        [
            ("每月卖7800杯，每个月营业26天。", {"sales": 300}),
            (
                "刚才说错了，7800其实是每月销售额7800元，不是7800杯。每杯15元，每月营业26天，月单量我还不确定，请先别估计。",
                {"sales": None},
            ),
        ],
    ),
]


async def main():
    app = create_app(Settings())
    factory = app.state.session_factory
    user_id = None
    results = []
    try:
        async with factory() as db:
            user = User(
                email=f"unit-review-{uuid4().hex}@example.com",
                password_hash="disabled-review-account",
                email_verified_at=utcnow(),
                daily_ai_quota=100,
            )
            db.add(user)
            await db.commit()
            user_id = user.id
        for name, previous, turns in CASES:
            async with factory() as db:
                profile = await create_profile(db, user_id, ProfileCreate(name=name, city="杭州"))
                run = AIRun(
                    user_id=user_id,
                    profile_id=profile.id,
                    request_id=uuid4(),
                    kind="interview",
                    status="succeeded",
                    model=app.state.settings.interview_model,
                    input={},
                    output={},
                    lease_until=utcnow() + timedelta(minutes=5),
                )
                conv = Conversation(profile_id=profile.id)
                db.add_all([run, conv])
                await db.flush()
                db.add(
                    Message(
                        conversation_id=conv.id,
                        run_id=run.id,
                        ordinal=0,
                        payload={"role": "assistant", "content": previous},
                        prompt_version=PROMPT_VERSION,
                    )
                )
                await db.commit()
                profile_id = profile.id
            for content, expected in turns:
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
                    profile = await get_owned_profile(db, user_id, profile_id)
                    p = profile.parameters

                    def base(section, key, parameters=p):
                        return (parameters[section][key] or {}).get("base")

                    staff = base("fixed_cost", "staff")
                    actual = {
                        "sales": base("revenue", "daily_orders"),
                        "rent": base("fixed_cost", "rent"),
                        "owner": base("fixed_cost", "owner_salary"),
                        "staff": sum(x["count"] * x["monthly_cost"] for x in staff)
                        if staff is not None
                        else None,
                    }
                    result = {
                        "case": name,
                        "input": content,
                        "expected": expected,
                        "actual": {k: actual[k] for k in expected},
                        "status": run.status,
                        "reply": run.output.get("content"),
                        "passed": run.status == "succeeded"
                        and all(actual[k] == v for k, v in expected.items()),
                        "input_tokens": run.input_tokens,
                        "output_tokens": run.output_tokens,
                    }
                    results.append(result)
                    if not result["passed"]:
                        messages = await db.scalars(
                            select(Message)
                            .where(Message.run_id == run_id)
                            .order_by(Message.ordinal)
                        )
                        result["diagnostics"] = [m.payload for m in messages]
                    print(json.dumps(result, ensure_ascii=False), flush=True)
        Path("../docs/访谈单位回归结果.json").write_text(
            json.dumps(
                {
                    "model": app.state.settings.interview_model,
                    "prompt_version": PROMPT_VERSION,
                    "cases": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if not all(result["passed"] for result in results):
            raise RuntimeError("单位回归存在失败，请检查结果文件")
    finally:
        if user_id:
            async with factory() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
        await app.state.ai_hub.close()
        await app.state.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
