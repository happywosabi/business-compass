"""先选题再写全文。首版使用有来源的固定日历与门店自有话题。"""

import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path

from app.db.base import utcnow
from app.db.models import AIRun, ContentDraft
from app.llm.runs import check_cancel, update_run

CALENDAR = [
    (1, 1, "元旦", "新年第一杯，聊聊今年的小期待"),
    (2, 14, "情人节", "适合一起分享的一杯与一段真心话"),
    (3, 8, "妇女节", "分享女性店员或顾客的日常，避免刻板印象"),
    (5, 1, "劳动节", "记录门店认真做一杯饮品的过程"),
    (6, 1, "儿童节", "找回童年口味记忆，不暗示儿童过量饮用"),
    (10, 1, "国庆节", "给附近出游或散步的人一份歇脚指南"),
    (12, 31, "年末", "记录这一年门店值得记住的小事"),
]
CALENDAR_SOURCE = None
PROMPT_VERSION = "content-3"
ORCHARD_PROMPT = Path(__file__).with_name("orchard_prompt.md").read_text()
PROMPT = Path(__file__).with_name("prompt.md").read_text()
PLACEHOLDER = re.compile(r"【待填：[^【】\n]+】")


def unsupported_details(content: str, data: dict) -> list[str]:
    confirmed = data.get("confirmed_facts", "")
    if data.get("template_key") == "orchard":
        confirmed += "。" + json.dumps(data.get("store", {}).get("supply", {}), ensure_ascii=False)
    facts = "。".join(
        clause
        for clause in re.split(r"[。；;，,\n]", confirmed)
        if not re.search(
            r"想写|想做|未(?:确定|提供|确认)|不知道|不确定|没有提供|没有.{0,8}(?:资料|数据|依据)|不(?:宣传|声称)",
            clause,
        )
    )
    # 完整的未知断言可留给用户填写；空位外仍不允许模型替用户编造具体事实。
    assertions = PLACEHOLDER.sub("", content)
    groups = [
        *(
            [
                r"有机|绿色认证|无农残",
                r"糖度|甜度|\d+(?:\.\d+)?度",
                r"包邮|免运费",
                r"当天到|次日达|隔日达|当天发货",
                r"产自|原产地",
                r"(?:进入|开始|正在|正值).{0,5}采收|采收期",
                r"统货.{0,12}(?:大小|没法|不能)|大小不一",
                r"第一时间补|按订单.{0,5}发货",
            ]
            if data.get("template_key") == "orchard"
            else []
        ),
        r"随机|盲盒",
        r"先到先选|先到先得",
        r"送完即止|数量有限|限量|限前\d+",
        r"现选|自选",
        r"以(?:门店|店里|现场).{0,8}为准",
        r"不搞复杂规则|没有额外(?:条件|门槛)",
        r"先不说喝什么.{0,4}周边先拿到手",
        r"低卡|减脂|无负担|\d+\s*(?:大卡|千卡|kcal)",
        r"销量|卖得最多|点得最多|人气最高|回购|内部员工|员工强推|每次有人问|每天被问|顾客都在问",
        r"天气热|降温|最近很热",
        r"热销|大家常点|点得多|最受欢迎",
        r"偏茶香|清爽|果味更浓",
    ]
    return [
        match.group()
        for pattern in groups
        for match in re.finditer(pattern, assertions)
        if not re.search(pattern, facts)
    ]


def topics(profile, today: date):
    if getattr(profile, "template_key", "physical_store") == "orchard":
        return [
            {
                "id": f"orchard:{k}",
                "title": title,
                "angle": angle,
                "date": None,
                "kind": "orchard",
                "sources": [
                    {
                        "title": f"{profile.name} · 果园供货档案",
                        "url": None,
                        "excerpt": f"生产地：{profile.city}；仅使用已确认供货资料。",
                        "retrieved_at": today.isoformat(),
                    }
                ],
            }
            for k, title, angle in [
                ("supply", "本季供货与合作说明", "向采购商介绍规格、供货期和起订量"),
                ("box", "这一箱水果怎么选", "向消费者讲清包装、规格与订购须知"),
                ("harvest", "果园采收日记", "用已确认的采收事实分享果园日常"),
            ]
        ]
    result = []
    for month, day, name, angle in CALENDAR:
        when = date(today.year, month, day)
        if when < today:
            when = date(today.year + 1, month, day)
        if when <= today + timedelta(days=45):
            result.append(
                {
                    "id": f"calendar:{when.isoformat()}",
                    "title": f"{name}的一杯心意",
                    "angle": angle,
                    "date": when.isoformat(),
                    "kind": "calendar",
                    "sources": [
                        {
                            "title": f"公历{month}月{day}日 · {name}（不代表调休安排）",
                            "url": CALENDAR_SOURCE,
                            "excerpt": f"围绕{name}进行提前策划，不声称放假或调休安排。",
                            "retrieved_at": today.isoformat(),
                        }
                    ],
                }
            )
    for key, title, angle in [
        ("process", "一杯饮品背后的认真", "拍一段真实制作过程，讲清一个你在意的细节"),
        ("neighborhood", "从街角出发的一次散步", "记录店铺附近真实可达的风景和生活场景"),
        ("question", "今天，你最想喝什么？", "邀请顾客分享口味偏好，真实倾听，不虚构顾客评价"),
    ]:
        result.append(
            {
                "id": f"evergreen:{key}",
                "title": title,
                "angle": angle,
                "date": None,
                "kind": "store",
                "sources": [
                    {
                        "title": f"{profile.name} · 商业档案",
                        "url": None,
                        "excerpt": f"城市：{profile.city}；业态：饮品。其余事实以用户补充为准。",
                        "retrieved_at": today.isoformat(),
                    }
                ],
            }
        )
    return result


async def write_draft(provider, data: dict, model: str):
    messages = [
        {
            "role": "system",
            "content": ORCHARD_PROMPT if data.get("template_key") == "orchard" else PROMPT,
        },
        {
            "role": "user",
            "content": "请根据以下素材写一份草稿，缺少的关键信息留具体待填项，供店主补齐后发布：\n"
            + json.dumps(data, ensure_ascii=False),
        },
    ]
    total_in, total_out = 0, 0
    for attempt in range(2):
        message, usage = await provider.complete(messages, model=model)
        total_in += usage.get("prompt_tokens", 0)
        total_out += usage.get("completion_tokens", 0)
        content = message.get("content") or ""
        unsupported = unsupported_details(content, data)
        if re.search(r"(?m)^\s*(?:#{1,6}\s|(?:标题|正文)[：:])", content):
            unsupported.append("不要Markdown标题、标题/正文标签或额外的待填项说明标题")
        if data.get("platform") == "moments" and "#" in content:
            unsupported.append("朋友圈不带话题标签")
        if len(PLACEHOLDER.findall(content)) > 3:
            unsupported.append("待填项超过3个，请只保留当前选题最有用的信息")
        if not unsupported:
            if not content or len(content) > 5000:
                raise ValueError("文案长度无效")
            return content, {"prompt_tokens": total_in, "completion_tokens": total_out}
        if attempt:
            raise ValueError("文案仍包含未确认的具体规则或过多待填项，请重试")
        messages += [
            message,
            {
                "role": "user",
                "content": "这份草稿添加了用户没有确认的细节："
                + "、".join(unsupported)
                + "。请将与选题有关的未知规则或断言整句改为【待填：具体要补什么】，每项单独一行，最多3项。"
                "已确认的内容保留；用户明确不写的内容省略。不要把未经确认的断言留在空位外，不要改成以现场为准或另编细节。"
                "保留具体看点和平台语气，重新输出完整草稿。",
            },
        ]


async def generate(app, run_id, draft_id):
    factory, settings = app.state.session_factory, app.state.settings
    try:
        async with asyncio.timeout(settings.ai_run_seconds):
            async with factory() as db:
                run, draft = await db.get(AIRun, run_id), await db.get(ContentDraft, draft_id)
                await check_cancel(factory, run_id)
                content, usage = await write_draft(app.state.llm, run.input, run.model)
                await check_cancel(factory, run_id)
                draft.content, draft.status = content, "succeeded"
                await db.commit()
                await update_run(
                    factory,
                    run_id,
                    status="succeeded",
                    output={"draft_id": str(draft.id)},
                    input_tokens=usage["prompt_tokens"],
                    output_tokens=usage["completion_tokens"],
                    finished_at=utcnow(),
                )
    except (Exception, asyncio.CancelledError):
        async with factory() as db:
            draft = await db.get(ContentDraft, draft_id)
            if draft:
                draft.status = "failed"
                await db.commit()
        await update_run(
            factory,
            run_id,
            status="failed",
            error="文案生成失败，输入已保留，请稍后重试",
            finished_at=utcnow(),
        )
