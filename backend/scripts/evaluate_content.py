"""使用虚构门店资料验证真实模型的平台文案；不写数据库、不发布内容。"""

import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.content.service import PROMPT_VERSION, unsupported_details, write_draft
from app.llm.provider import DeepSeekProvider


async def main():
    settings = Settings()
    provider = DeepSeekProvider(settings)
    cases = [
        (
            "小红书·周边福利",
            "xiaohongshu",
            "warm",
            "今天到店买奶茶会送哪吒周边。未确定周边款式和数量，不宣传折扣。",
        ),
        (
            "小红书·真实菜单",
            "xiaohongshu",
            "playful",
            "店内确有茉莉奶绿、柠檬红茶、芒果冰茶三款。茉莉奶绿可选三分糖加珍珠；柠檬红茶可选少冰；芒果冰茶可选五分糖。没有热量资料。",
        ),
        (
            "朋友圈·制作日常",
            "moments",
            "simple",
            "今天拍了手工煮茶的视频。没有促销活动，不声称现煮现售。",
        ),
        (
            "小红书·热销资料缺失",
            "xiaohongshu",
            "playful",
            "想写一份本店热销饮品推荐，但还没有提供饮品名字和销量统计。请留出可填的位置。",
        ),
    ]
    results = []
    for name, platform, voice, facts in cases:
        data = {
            "store": {"name": "哪吒仙饮", "city": "深圳"},
            "platform": platform,
            "voice": voice,
            "confirmed_facts": facts,
            "topic": {
                "title": "本店热销饮品推荐" if "热销" in name else "今天，你最想喝什么？",
                "angle": "分享真实的门店内容，邀请大家交流口味偏好",
                "sources": [],
            },
        }
        content, usage = await write_draft(provider, data, settings.interview_model)
        result = {
            "case": name,
            "input": data,
            "content": content,
            "usage": usage,
            "unsupported_details": unsupported_details(content, data),
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    Path("../docs/文案回归样例.json").write_text(
        json.dumps(
            {"model": settings.interview_model, "prompt_version": PROMPT_VERSION, "cases": results},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
