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
    if snapshot.results.get("kind") == "fruit_retail":
        return {
            "元": [
                base[k]
                for k in (
                    "monthly_revenue",
                    "monthly_procurement",
                    "fixed_cost",
                    "monthly_net",
                    "monthly_net_excl_owner",
                    "break_even_monthly",
                    "break_even_daily",
                    "reference_stock",
                    "stock_shortfall",
                    "startup_investment",
                    "funding_required",
                    "cash_shortfall",
                )
                if base[k] is not None
            ],
            "月": [36, 120]
            + [
                base[k]
                for k in ("payback_month", "payback_month_excl_owner", "runway_months")
                if base[k] is not None
            ],
            "%": [base["procurement_ratio"] * 100, base["contribution_rate"] * 100],
        }
    if snapshot.template_key == "orchard":
        return {
            "元": [
                base[k]
                for k in (
                    "revenue",
                    "operating_expense",
                    "operating_surplus",
                    "labor_adjusted_earnings",
                    "unpaid_labor",
                    "equipment_purchases",
                    "shared_cost",
                )
                if base[k] is not None
            ],
            "kg": [base["sold_kg"]],
            "元/kg": [base["break_even_price"]] if base["break_even_price"] is not None else [],
        }
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
    pattern = re.compile(r"([−-]?\d[\d,]*(?:\.\d+)?)\s*(元/kg|kg|万?元|万|个月|月|杯|单|%|％)")
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


def report_material(snapshot):
    """模型只接收有含义的可引用结果，避免把无标签数字或其他场景混在一起。"""
    base = snapshot.results["scenarios"]["base"]
    if snapshot.results.get("kind") == "fruit_retail":
        labels = {
            "monthly_revenue": "月营业额",
            "monthly_procurement": "月采购成本（含损耗）",
            "monthly_net": "扣老板报酬月结余",
            "monthly_net_excl_owner": "未扣老板报酬月结余",
            "break_even_monthly": "保本月营业额",
            "break_even_daily": "保本日营业额",
            "reference_stock": "参考备货资金",
            "stock_shortfall": "备货缺口",
            "funding_required": "本次所需资金",
            "startup_investment": "筹备启动投入",
            "cash_shortfall": "已知现金下的即时资金缺口",
        }
        return {
            **{
                label: f"{base[k]:g}元" if base[k] is not None else "未知或不适用"
                for k, label in labels.items()
            },
            "预测阶段": "经营中，只预测未来"
            if snapshot.results["stage"] == "operating"
            else "筹备开店",
            "边界": snapshot.results["assumptions"],
            "回本预测": f"{base['payback_month']}个月"
            if base["payback_month"] is not None
            else "经营中不计算历史回本"
            if snapshot.results["stage"] == "operating"
            else "120个月内未回本",
            "现金可用期": f"{base['runway_months']:g}个月"
            if base["runway_months"] is not None
            else "未知或无持续亏损",
            "是否已提供范围": bool(snapshot.results["sensitivity"]),
        }
    if snapshot.template_key == "orchard":
        return {
            "本期收入": f"{base['revenue']:g}元",
            "经营支出": f"{base['operating_expense']:g}元",
            "经营结余": f"{base['operating_surplus']:g}元",
            "扣家庭劳动估值后收益": f"{base['labor_adjusted_earnings']:g}元",
            "保本均价": f"{base['break_even_price']:g}元/kg"
            if base["break_even_price"] is not None
            else "无有限值",
            "边界": snapshot.results["assumptions"],
            "是否已提供不确定范围": bool(snapshot.results["sensitivity"]),
        }
    material = {
        "稳定期月营业额": f"{base['steady_monthly_revenue']:g}元",
        "稳定期每月固定成本": f"{base['steady_fixed_cost']:g}元",
        "稳定期每月现金结余（扣老板工资）": f"{base['steady_monthly_cash']:g}元",
        "稳定期每月现金结余（未扣老板工资）": f"{base['steady_monthly_cash_excl_owner']:g}元",
        "回本时间": f"第{base['payback_month']}个月" if base["payback_month"] else "推演内未回本",
        "租约内回本": base["lease_check"] == "pass",
        "参数需核实": snapshot.results["default_keys"],
        "是否已提供不确定范围": bool(snapshot.results["sensitivity"]),
    }
    if base["suggested_funding"]:
        lo, hi = base["suggested_funding"]
        material["准备资金范围"] = f"{lo:g}元至{hi:g}元"
    else:
        material["准备资金范围"] = "稳定期未盈利，无法给出有限资金建议"
    return material


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
                    "禁止用汉字写金额、月份或百分比，必须保留阿拉伯数字及原含义。"
                    "不要数字编号，不引用年份和引擎版本。结论只能是需要进一步核实，不能说可以投入、建议开店、低于某数就不要开等投资指令。没有三档范围时说明需补范围。稳定期亏钱时不得给出有限资金建议。不保证赚钱。\n可引用结果（键是含义，值是带单位的计算结果）："
                    + json.dumps(report_material(snapshot), ensure_ascii=False)
                )
                if snapshot.template_key == "orchard":
                    prompt = (
                        "你是商业罗盘，用大白话简短解读在产果园经营期总账。只引用材料数字，不自行计算；数字紧跟元或元/kg单位，不写数字编号。必须说明全部销售款收齐假设，不声称现金流、建园回本或投资建议。区分经营结余与扣未付酬家庭劳动估值后收益，说明核实产量、售价、损耗及销路的方法；没有范围请提醒补充，不编农业基准。材料："
                        + json.dumps(report_material(snapshot), ensure_ascii=False)
                    )
                if snapshot.results.get("kind") == "fruit_retail":
                    prompt = (
                        "你是商业罗盘，用不超过400字解读水果零售整店预测，不写开场白。只能引用材料中带单位的数字，不自行运算，不写数字编号。数字紧跟元、个月或%，禁止用汉字写金额、月份、百分比；引用数字必须使用阿拉伯数字和元/个月/%单位。不写数字编号。禁止输出材料之外的数字，禁止把材料中的数字改变含义；可只引用月结余和备货资金，其他用文字概括。没有范围提醒补范围。清楚区分扣/未扣老板报酬的结余、采购成本与备货占用。经营中只预测从现在起的未来，不能声称历史利润或历史回本；现金未知不能推断缺口或能撑多久。筹备亏损时资金需求只是启动与备货，不是足够撑住经营的总资金保证。给出可执行的核实办法，不编行业基准，不给投入建议。材料："
                        + json.dumps(report_material(snapshot), ensure_ascii=False)
                    )
                content, accepted, total_in, total_out = "", False, 0, 0
                for attempt in range(2):
                    await check_cancel(factory, run_id)
                    message, usage = await app.state.llm.complete(
                        [
                            {
                                "role": "system",
                                "content": (
                                    "用简短自然语言说明水果零售店需要核实的假设和操作方法：销售是否实现、采购是否含损耗、库存是否积压、老板劳动报酬是否单列。严禁任何阿拉伯数字或汉字数量、金额、时间长度；不引用测算数值，不讨论几年或几个月，不给出回本或投资承诺。仅用短段落，不编号。"
                                    if attempt and snapshot.results.get("kind") == "fruit_retail"
                                    else prompt
                                ),
                            },
                            {
                                "role": "user",
                                "content": "请解读这份结果。"
                                if attempt == 0
                                else "上次数字核对未通过。这次完全不写任何金额、月份、比例或数字，只说明需要核实的假设和低成本验证方法。不要重复未核实的数字。",
                            },
                        ],
                        model=run.model,
                        thinking=False,
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
                report.content = (
                    content
                    + "\n\n"
                    + (
                        "测算基于用户提供的估计，假定销售款全部收齐，不构成投资建议。"
                        if snapshot.template_key == "orchard"
                        else "测算基于用户确认的水果店经营假设，不构成投资建议。"
                        if snapshot.results.get("kind") == "fruit_retail"
                        else DISCLAIMER
                    )
                    if accepted
                    else None
                )
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
            if report and report.run_id == run_id:
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
