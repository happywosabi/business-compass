"""模板分发：参数、元数据、就绪规则与计算器保持同一入口。"""

from datetime import date
from types import SimpleNamespace
from typing import Any

from app.engine import CheckRules, PhysicalStoreParams, evaluate, what_if
from app.engine.orchard import ORCHARD_KEYS, OrchardParams, evaluate_orchard, orchard_what_if
from app.engine.params import ALL_KEYS

Parameters = PhysicalStoreParams | OrchardParams
PARAMETER_MODELS = {"physical_store": PhysicalStoreParams, "orchard": OrchardParams}


def parameter_model(key: str) -> type[PhysicalStoreParams] | type[OrchardParams]:
    if key not in PARAMETER_MODELS:
        raise KeyError(f"未知模板：{key}")
    return PARAMETER_MODELS[key]


def parse_parameters(key: str, data: Any) -> Parameters:
    return parameter_model(key).model_validate(data)


def parameter_keys(params: Parameters) -> tuple[str, ...]:
    return ORCHARD_KEYS if isinstance(params, OrchardParams) else ALL_KEYS


def calculate(params: Parameters, rules: CheckRules | None = None):
    return (
        evaluate_orchard(params) if isinstance(params, OrchardParams) else evaluate(params, rules)
    )


def preview(params: Parameters, changes: dict[str, Any]):
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
