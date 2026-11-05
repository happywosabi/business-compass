"""模板分发：参数、元数据、就绪规则与计算器保持同一入口。"""

from datetime import date
from types import SimpleNamespace
from typing import Any

from app.engine import CheckRules, PhysicalStoreParams, evaluate, what_if
from app.engine.fruit_retail import FRUIT_KEYS, FruitRetailParams, evaluate_fruit, fruit_what_if
from app.engine.orchard import ORCHARD_KEYS, OrchardParams, evaluate_orchard, orchard_what_if
from app.engine.params import ALL_KEYS

Parameters = PhysicalStoreParams | OrchardParams | FruitRetailParams
PARAMETER_MODELS = {"physical_store": PhysicalStoreParams, "orchard": OrchardParams}


def parameter_model(
    key: str, industry: str | None = None
) -> type[PhysicalStoreParams] | type[OrchardParams] | type[FruitRetailParams]:
    if key == "physical_store" and industry == "fruit_retail":
        return FruitRetailParams
    if key not in PARAMETER_MODELS:
        raise KeyError(f"未知模板：{key}")
    return PARAMETER_MODELS[key]


def parse_parameters(key: str, data: Any) -> Parameters:
    if key == "physical_store" and isinstance(data, dict) and data.get("schema_version") == 3:
        return FruitRetailParams.model_validate(data)
    return parameter_model(key).model_validate(data)


def parameter_keys(params: Parameters) -> tuple[str, ...]:
    if isinstance(params, FruitRetailParams):
        return FRUIT_KEYS
    return ORCHARD_KEYS if isinstance(params, OrchardParams) else ALL_KEYS


def calculate(params: Parameters, rules: CheckRules | None = None):
    if isinstance(params, FruitRetailParams):
        return evaluate_fruit(params)
    return (
        evaluate_orchard(params) if isinstance(params, OrchardParams) else evaluate(params, rules)
    )


def preview(params: Parameters, changes: dict[str, Any]):
    if isinstance(params, FruitRetailParams):
        return fruit_what_if(params, changes)
    return (
        orchard_what_if(params, changes)
        if isinstance(params, OrchardParams)
        else what_if(params, changes)
    )


class OrchardTemplate:
    key = "orchard"
    version = 1
    industry_codes = ["fruit_grower"]

    def __init__(self, specs: list):
        self.specs = {s.key: s for s in specs}
        if set(self.specs) != set(ORCHARD_KEYS):
            raise ValueError("果园字段配置与参数结构不一致")

    @property
    def quick_required_keys(self) -> list[str]:
        return [k for k, s in self.specs.items() if s.quick_required]

    def industry(self, code: str) -> SimpleNamespace:
        if code != "fruit_grower":
            raise KeyError("果园档案仅支持在产果园")
        return SimpleNamespace(label="在产果园", params={}, derived={})

    def quick_missing(self, params: OrchardParams) -> list[str]:
        return params.missing_keys()

    def fill_defaults(
        self, params: OrchardParams, industry: str, today: date | None = None
    ) -> tuple[OrchardParams, list[str]]:
        self.industry(industry)
        return params, []

    def check_rules(self, code: str) -> None:
        self.industry(code)
        return None


class FruitTemplate:
    key = "physical_store"
    version = 1
    industry_codes = ["fruit_retail"]

    def __init__(self, specs):
        self.specs = {s.key: s for s in specs}
        if set(self.specs) != set(FRUIT_KEYS):
            raise ValueError("水果店字段配置不一致")

    @property
    def quick_required_keys(self):
        return FruitRetailParams().required_keys()

    def industry(self, code):
        if code != "fruit_retail":
            raise KeyError("水果零售档案业态不匹配")
        return SimpleNamespace(label="水果店（零售）", params={}, derived={})

    def quick_missing(self, params):
        return params.missing_keys()

    def fill_defaults(self, params, industry, today=None):
        self.industry(industry)
        return params, []

    def check_rules(self, code):
        self.industry(code)
        return None
