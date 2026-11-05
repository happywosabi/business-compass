"""水果零售整店前瞻测算。纯计算；不读取时间、文件或行业默认值。"""

from collections.abc import Mapping
from datetime import date
from math import ceil
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .orchard import Amount, Strict
from .params import SCENARIOS, DaysPerMonth, MissingParametersError, ParamValue, Rate, Source


class PublicFacts(Strict):
    products: str | None = Field(default=None, max_length=1000)
    retail_prices: str | None = Field(default=None, max_length=1000)
    confirmed_origin: str | None = Field(default=None, max_length=500)
    delivery_rules: str | None = Field(default=None, max_length=1000)
    promotions: str | None = Field(default=None, max_length=1000)


class FruitSection(Strict):
    revenue_basis: ParamValue[Literal["revenue", "transactions"]] | None = None
    sales_amount: Amount | None = None
    sales_period: ParamValue[Literal["day", "month"]] | None = None
    daily_transactions: Amount | None = None
    avg_ticket: Amount | None = None
    open_days: ParamValue[DaysPerMonth] | None = None
    cost_basis: ParamValue[Literal["margin_loss", "inclusive"]] | None = None
    gross_margin: ParamValue[Rate] | None = None
    loss_rate: ParamValue[Rate] | None = None
    procurement_ratio: ParamValue[Annotated[float, Field(ge=0)]] | None = None
    packaging_rate: ParamValue[Rate] | None = None
    channel_rate: ParamValue[Rate] | None = None
    payment_tax_rate: ParamValue[Rate] | None = None
    rent: Amount | None = None
    staff_cost: Amount | None = None
    owner_salary: Amount | None = None
    utilities: Amount | None = None
    delivery_fixed: Amount | None = None
    other_fixed: Amount | None = None
    renovation: Amount | None = None
    equipment: Amount | None = None
    deposit: Amount | None = None
    stock: Amount | None = None
    stocking_days: Amount | None = None
    available_cash: Amount | None = None
    area_sqm: Amount | None = None
    location: ParamValue[Annotated[str, Field(max_length=300)]] | None = None
    channels: ParamValue[Annotated[str, Field(max_length=500)]] | None = None
    public_facts: ParamValue[PublicFacts] | None = None


FRUIT_KEYS = tuple(f"fruit.{k}" for k in FruitSection.model_fields)
COMMON = tuple(
    f"fruit.{k}"
    for k in (
        "revenue_basis",
        "open_days",
        "cost_basis",
        "packaging_rate",
        "channel_rate",
        "payment_tax_rate",
        "rent",
        "staff_cost",
        "owner_salary",
        "utilities",
        "delivery_fixed",
        "other_fixed",
        "stock",
        "stocking_days",
    )
)
HIGH_GOOD = {"sales_amount", "daily_transactions", "avg_ticket", "gross_margin", "available_cash"}


class FruitRetailParams(Strict):
    schema_version: Literal[3] = 3
    stage: Literal["idea", "preparing", "operating"] = "idea"
    forecast_start: date | None = None
    fruit: FruitSection = Field(default_factory=FruitSection)

    @model_validator(mode="after")
    def validate_modes(self) -> "FruitRetailParams":
        f = self.fruit
        if f.cost_basis:
            inactive = (
                ("procurement_ratio",)
                if f.cost_basis.base == "margin_loss"
                else (
                    "gross_margin",
                    "loss_rate",
                )
            )
            if any(getattr(f, k) is not None for k in inactive):
                raise ValueError("两种采购成本口径互斥，请清空另一口径后保存")
        if f.revenue_basis:
            inactive = (
                ("daily_transactions", "avg_ticket")
                if f.revenue_basis.base == "revenue"
                else (
                    "sales_amount",
                    "sales_period",
                )
            )
            if any(getattr(f, k) is not None for k in inactive):
                raise ValueError("营业额与笔数×客单价口径互斥，请清空另一口径")
        for key in FRUIT_KEYS:
            value = self.get(key)
            if value is None:
                continue
            name = key.split(".")[1]
            for tier in ("pessimistic", "optimistic"):
                n = getattr(value, tier)
                if n is None:
                    continue
                if not isinstance(value.base, (int, float)):
                    raise ValueError("仅数值支持三档范围")
                if name in {"open_days", "area_sqm", "stock", "stocking_days"}:
                    raise ValueError("营业天数、面积、库存与备货天数使用中性值；请用试算比较")
                if (
                    (n > value.base)
                    if (name in HIGH_GOOD) == (tier == "pessimistic")
                    else (n < value.base)
                ):
                    raise ValueError("三档方向有误：营业额和毛利率悲观较低，成本和损耗悲观较高")
        if f.loss_rate and any(f.loss_rate.get(s) >= 1 for s in SCENARIOS):
            raise ValueError("损耗率100%无法形成持续销售，请核实损耗口径")
        return self

    def get(self, key: str) -> ParamValue[Any] | None:
        if key not in FRUIT_KEYS:
            raise KeyError(f"未知水果店参数：{key}")
        return getattr(self.fruit, key.split(".")[1])

    def with_values(self, changes: Mapping[str, Any]) -> "FruitRetailParams":
        data = self.model_dump(mode="json")
        for key, value in changes.items():
            self.get(key)
            if isinstance(value, ParamValue):
                value = value.model_dump(mode="json")
            elif value is not None and not (isinstance(value, dict) and "base" in value):
                value = {"base": value}
            data["fruit"][key.split(".")[1]] = value
        return FruitRetailParams.model_validate(data)

    def required_keys(self) -> list[str]:
        keys = list(COMMON)
        f = self.fruit
        keys += [
            f"fruit.{k}"
            for k in (
                ("daily_transactions", "avg_ticket")
                if f.revenue_basis and f.revenue_basis.base == "transactions"
                else ("sales_amount", "sales_period")
            )
        ]
        keys += [
            f"fruit.{k}"
            for k in (
                ("procurement_ratio",)
                if f.cost_basis and f.cost_basis.base == "inclusive"
                else ("gross_margin", "loss_rate")
            )
        ]
        if self.stage != "operating":
            keys += ["fruit.renovation", "fruit.equipment", "fruit.deposit"]
        return keys

    def missing_keys(self) -> list[str]:
        return [k for k in self.required_keys() if self.get(k) is None]

    def keys_by_source(self, source: Source) -> list[str]:
        return [k for k in FRUIT_KEYS if self.get(k) and self.get(k).source == source]


class FruitMonth(Strict):
    t: int
    revenue: float
    cash_flow: float
    cash: float


class FruitScenario(Strict):
    monthly_revenue: float
    monthly_procurement: float
    procurement_ratio: float
    contribution_rate: float
    fixed_cost: float
    monthly_net: float
    monthly_net_excl_owner: float
    break_even_monthly: float | None
    break_even_daily: float | None
    reference_stock: float
    stock_shortfall: float
    startup_investment: float | None
    funding_required: float
    payback_month: int | None
    payback_month_excl_owner: int | None
    cash_shortfall: float | None
    runway_months: float | None
    monthly: list[FruitMonth]


class FruitRetailResult(Strict):
    kind: Literal["fruit_retail"] = "fruit_retail"
    engine_version: str = "fruit-retail-1"
    stage: Literal["idea", "preparing", "operating"]
    forecast_start: date | None
    scenarios: dict[str, FruitScenario]
    sensitivity: list[dict[str, Any]]
    checks: list[Any] = Field(default_factory=list)
    default_keys: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "按现销、采购即付、库存稳定推演未来36个月；无默认爬坡、季节性或行业税率。",
            "未损耗毛利率以销售额为分母；损耗按采购成本加权。含损耗采购成本率不再扣损耗。",
            "采购付款额受库存变动影响，不能直接用当月采购付款/销售额代替采购成本率。",
            "库存按进货成本记录，是资金占用，不再作为每月额外支出；超额库存不假设原价变现。",
            "经营中只预测未来；历史装修、设备、押金不重复扣除，不计算历史回本。",
        ]
    )


def _scenario(params: FruitRetailParams, s: str) -> FruitScenario:
    def n(key: str) -> float:
        v = params.get(f"fruit.{key}")
        return v.get(s) if v else 0

    f = params.fruit
    days = n("open_days")
    revenue = (
        n("sales_amount") * (days if f.sales_period.base == "day" else 1)
        if f.revenue_basis.base == "revenue"
        else n("daily_transactions") * n("avg_ticket") * days
    )
    ratio = (
        (1 - n("gross_margin")) / (1 - n("loss_rate"))
        if f.cost_basis.base == "margin_loss"
        else n("procurement_ratio")
    )
    procurement = revenue * ratio
    contribution = 1 - ratio - n("packaging_rate") - n("channel_rate") - n("payment_tax_rate")
    fixed = sum(
        n(k)
        for k in (
            "rent",
            "staff_cost",
            "owner_salary",
            "utilities",
            "delivery_fixed",
            "other_fixed",
        )
    )
    net = revenue * contribution - fixed
    excl = net + n("owner_salary")
    reference = procurement / days * n("stocking_days")
    shortfall = max(reference - n("stock"), 0)
    startup = (
        sum(n(k) for k in ("renovation", "equipment", "deposit", "stock"))
        if params.stage != "operating"
        else None
    )
    funding = (startup or 0) + shortfall

    def payback(profit):
        if startup is None or profit <= 0:
            return None
        month = ceil(funding / profit)
        return month if month <= 120 else None

    known_cash = f.available_cash is not None
    cash = n("available_cash") - funding if known_cash else -funding
    return FruitScenario(
        monthly_revenue=revenue,
        monthly_procurement=procurement,
        procurement_ratio=ratio,
        contribution_rate=contribution,
        fixed_cost=fixed,
        monthly_net=net,
        monthly_net_excl_owner=excl,
        break_even_monthly=fixed / contribution if contribution > 0 else None,
        break_even_daily=fixed / contribution / days if contribution > 0 else None,
        reference_stock=reference,
        stock_shortfall=shortfall,
        startup_investment=startup,
        funding_required=funding,
        payback_month=payback(net),
        payback_month_excl_owner=payback(excl),
        cash_shortfall=max(-cash, 0) if known_cash else None,
        runway_months=max(cash, 0) / -net if known_cash and net < 0 else None,
        monthly=[
            FruitMonth(
                t=t,
                revenue=revenue if t else 0,
                cash_flow=net if t else -funding,
                cash=cash + t * net,
            )
            for t in range(37)
        ],
    )


def evaluate_fruit(params: FruitRetailParams) -> FruitRetailResult:
    if missing := params.missing_keys():
        raise MissingParametersError(missing)
    scenarios = {s: _scenario(params, s) for s in SCENARIOS}
    sensitivity = []
    for key in FRUIT_KEYS:
        v = params.get(key)
        if not v or not v.has_range:
            continue
        for s in ("pessimistic", "optimistic"):
            changed = params.with_values({key: {"base": v.get(s)}})
            sensitivity.append(
                {
                    "key": key,
                    "scenario": s,
                    "delta": _scenario(changed, "base").monthly_net - scenarios["base"].monthly_net,
                }
            )
    return FruitRetailResult(
        stage=params.stage,
        forecast_start=params.forecast_start,
        scenarios=scenarios,
        sensitivity=sorted(sensitivity, key=lambda r: abs(r["delta"]), reverse=True),
    )


class FruitWhatIf(Strict):
    baseline: FruitRetailResult
    modified: FruitRetailResult
    surplus_delta: float


def fruit_what_if(params: FruitRetailParams, changes: Mapping[str, Any]) -> FruitWhatIf:
    before, after = evaluate_fruit(params), evaluate_fruit(params.with_values(changes))
    return FruitWhatIf(
        baseline=before,
        modified=after,
        surplus_delta=after.scenarios["base"].monthly_net - before.scenarios["base"].monthly_net,
    )
