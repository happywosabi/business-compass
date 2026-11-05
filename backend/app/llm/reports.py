"""结果解读单独生成并核对数字；不通过时只保留确定性的数字卡片。"""

import asyncio
import json
import logging
import re
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.auth.dependencies import CurrentUser, VerifiedUser
from app.db.base import utcnow
from app.db.models import AIRun, EvaluationReport
from app.deps import DB, AppSettings
from app.evaluations import service as evaluations
from app.interview.router import run_out
from app.llm.runs import check_cancel, reserve, update_run
from app.profiles import service as profiles
from app.profiles.schemas import StrictBody

router = APIRouter(
    prefix="/api/profiles/{profile_id}/evaluations/{evaluation_id}/report", tags=["AI解读"]
)
logger = logging.getLogger(__name__)
DISCLAIMER = "测算结果基于用户提供的估计和行业默认值，不构成投资建议。"


def facts(snapshot):
    base = snapshot.results["scenarios"]["base"]
    # 限定有语义单位的允许数字，避免把百分比误当金额，或用模型自己凑出的数字。
    result = {"元": [], "月": [], "单": [], "%": []}
    for key in [
        "steady_monthly_revenue",
        "steady_fixed_cost",
        "steady_monthly_cash",
        "steady_monthly_cash_excl_owner",
        "unit_margin",
    ]:
        result["元"].append(base[key])
    for v in base["suggested_funding"] or []:
        result["元"].append(v)
    if base["cash_low"]:
        result["元"].append(base["cash_low"]["amount"])
        result["月"].append(base["cash_low"]["month"])
    for key in ["payback_month", "first_profitable_month", "lease_months"]:
        if base[key] is not None:
            result["月"].append(base[key])
    threshold = snapshot.results["thresholds"]["revenue.daily_orders"]["value"]
    if threshold is not None:
        import math

        result["单"].append(math.ceil(round(threshold, 6)))
    if snapshot.results["safety_margin"] is not None:
        result["%"].append(snapshot.results["safety_margin"] * 100)
    return result


def verify_numbers(text: str, allowed: dict) -> bool:
    if re.search(
        r"(?<![\d.])[零〇一二两三四五六七八九十百千万亿点]+(?:元|个月|杯|单)|百分之[零〇一二两三四五六七八九十百千万亿点]+",
        text,
    ):
        return False
    # 要求阿拉伯数字紧随明确单位。顺序编号和自造数字同样不放行。
    pattern = re.compile(r"([−-]?\d[\d,]*(?:\.\d+)?)\s*(万?元|万|个月|月|杯|单|%|％)")
    spans = []
    for match in pattern.finditer(text):
        raw, unit = match.groups()
        number = Decimal(raw.replace(",", "").replace("−", "-"))
        if unit in {"万元", "万"}:
            factor, target = Decimal(10000), "元"
        else:
            factor, target = Decimal(1), {"个月": "月", "杯": "单", "％": "%"}.get(unit, unit)
        # 四舍五入误差仅允许半个末位，例如34万元允许335000–345000。
        decimal_places = len(raw.split(".")[1]) if "." in raw else 0
        tolerance = factor * Decimal(10) ** -decimal_places / 2
        if not any(
            abs(number * factor - Decimal(str(v))) <= tolerance for v in allowed.get(target, [])
        ):
            return False
        spans.append(match.span())
    remaining = list(text)
    for start, end in spans:
        remaining[start:end] = " " * (end - start)
    return not re.search(r"\d", "".join(remaining))


async def generate(app, run_id, snapshot):
    factory, settings = app.state.session_factory, app.state.settings
    try:
        async with asyncio.timeout(settings.ai_run_seconds):
            async with factory() as db:
                run = await db.get(AIRun, run_id)
                allowed = facts(snapshot)
                prompt = (
                    "你是商业罗盘，用大白话写简短的开店解读，最多600字。包括投入判断的边界、需要核实的假设、低成本验证方法。"
                    "只能引用允许数字表中的数字，不自行计算。阿拉伯数字后必须紧跟单位（元、万元、个月、杯、%）；每个范围端点各带单位。"
                    "不要数字编号，不引用年份和引擎版本。结论只能是需要进一步核实，不能说可以投入、建议开店、低于某数就不要开等投资指令。没有三档范围时说明需补范围。稳定期亏钱时不得给出有限资金建议。不保证赚钱。\n允许数字："
                    + json.dumps(allowed, ensure_ascii=False)
                    + "\n工具摘要："
                    + json.dumps(
                        {
                            "summary": snapshot.summary,
                            "scenarios": {
                                k: {key: value for key, value in v.items() if key != "monthly"}
                                for k, v in snapshot.results["scenarios"].items()
                            },
                            "checks": snapshot.results["checks"],
                            "sensitivity": snapshot.results["sensitivity"][:3],
                            "default_keys": snapshot.results["default_keys"],
                        },
                        ensure_ascii=False,
                    )
                )
                content, accepted, total_in, total_out = "", False, 0, 0
                for attempt in range(2):
                    await check_cancel(factory, run_id)
                    message, usage = await app.state.llm.complete(
                        [
                            {"role": "system", "content": prompt},
                            {
                                "role": "user",
                                "content": "请解读这份结果。"
                                if attempt == 0
                                else "上次数字核对未通过。只引用允许数字表中带单位的值，无法核实就省略数字。",
                            },
                        ],
                        model=run.model,
                    )
                    total_in += usage.get("prompt_tokens", 0)
                    total_out += usage.get("completion_tokens", 0)
                    content = message.get("content") or ""
                    accepted = bool(content) and verify_numbers(content, allowed)
                    if accepted:
                        break
                await check_cancel(factory, run_id)
                report = await db.scalar(
                    select(EvaluationReport).where(EvaluationReport.evaluation_id == snapshot.id)
                )
                report.status = "succeeded" if accepted else "failed"
                report.content = content + "\n\n" + DISCLAIMER if accepted else None
                await db.commit()
                await update_run(
                    factory,
                    run_id,
                    status="succeeded" if accepted else "failed",
                    output={"report_status": report.status},
                    error=None if accepted else "数字核对未通过，请以关键数字卡片为准",
                    input_tokens=total_in,
                    output_tokens=total_out,
                    finished_at=utcnow(),
                )
    except (Exception, asyncio.CancelledError) as error:
        logger.info("Report run %s ended: %s %s", run_id, type(error).__name__, str(error)[:180])
        async with factory() as db:
            report = await db.scalar(
                select(EvaluationReport).where(EvaluationReport.evaluation_id == snapshot.id)
            )
            if report:
                report.status, report.content = "failed", None
                await db.commit()
        await update_run(
            factory,
            run_id,
            status="failed",
            error="解读生成失败，请以数字卡片为准，稍后重试",
            finished_at=utcnow(),
        )


class Generate(StrictBody):
    request_id: UUID


@router.get("")
async def get_report(profile_id: UUID, evaluation_id: UUID, db: DB, user: CurrentUser):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    snapshot = await evaluations.get_snapshot(db, profile, evaluation_id)
    item = await db.scalar(
        select(EvaluationReport).where(EvaluationReport.evaluation_id == snapshot.id)
    )
    if item is None:
        return {"status": "missing", "content": None}
    run = await db.get(AIRun, item.run_id)
    if item.status == "running" and (run.status != "running" or run.lease_until < utcnow()):
        item.status = "failed"
        await db.commit()
    return {"status": item.status, "content": item.content, "run": run_out(run)}


@router.post("")
async def create_report(
    profile_id: UUID,
    evaluation_id: UUID,
    body: Generate,
    request: Request,
    db: DB,
    settings: AppSettings,
    user: VerifiedUser,
):
    profile = await profiles.get_owned_profile(db, user.id, profile_id)
    snapshot = await evaluations.get_snapshot(db, profile, evaluation_id)
    cached = await db.scalar(
        select(EvaluationReport).where(EvaluationReport.evaluation_id == evaluation_id)
    )
    if cached and cached.status == "succeeded":
        return {"status": "succeeded"}
    run, created = await reserve(
        db,
        user,
        profile_id,
        body.request_id,
        "report",
        {"evaluation_id": str(evaluation_id)},
        settings,
    )
    if not created:
        return run_out(run)
    existing = await db.scalar(
        select(EvaluationReport)
        .where(EvaluationReport.evaluation_id == evaluation_id)
        .with_for_update()
    )
    if existing and existing.status == "succeeded":
        await update_run(
            request.app.state.session_factory,
            run.id,
            status="succeeded",
            output={"report_status": "succeeded"},
            finished_at=utcnow(),
        )
        return {"status": "succeeded"}
    if existing:
        existing.run_id, existing.status, existing.content = run.id, "running", None
    else:
        db.add(EvaluationReport(evaluation_id=evaluation_id, run_id=run.id, status="running"))
    await db.commit()
    request.app.state.ai_hub.start(run.id, generate(request.app, run.id, snapshot))
    return run_out(run)
