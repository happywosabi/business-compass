"""读取模板配置（YAML），按业态给参数补默认值。

模板配置是"内容"：问法、默认值、经验阈值，修改后不需要改代码。
计算引擎不读文件，由这里读好后传给引擎。
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.engine import CheckRules, PhysicalStoreParams, TrafficDefaults
from app.engine.params import ALL_KEYS

TEMPLATES_DIR = Path(__file__).parent

Stage = Literal["basic", "product", "shop", "costs", "traffic", "none"]


class ParamSpec(BaseModel):
    """一个参数的界面和访谈配置。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str | None = None
    stage: Stage
    quick_required: bool = False
    three_tier: bool = False
    ask: str | None = None
    ask_alternative: str | None = None
    ask_range: str | None = None


class DerivedDefault(BaseModel):
    """按其他参数推算的默认值：值 = 参照参数的中性值 × 比例。"""

    model_config = ConfigDict(extra="forbid")

    ratio_of: str
    ratio: float


class IndustryDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    params: dict[str, Any] = Field(default_factory=dict)
    derived: dict[str, DerivedDefault] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    traffic: TrafficDefaults


class Template:
    """一个评估模板的全部配置。"""

    def __init__(
        self,
        key: str,
        specs: list[ParamSpec],
        industries: dict[str, IndustryDefaults],
        checks: dict[str, CheckRules],
    ):
        spec_keys = [s.key for s in specs]
        if sorted(spec_keys) != sorted(ALL_KEYS):
            missing = sorted(set(ALL_KEYS) - set(spec_keys))
            extra = sorted(set(spec_keys) - set(ALL_KEYS))
            raise ValueError(f"parameters.yaml 与参数结构不一致：缺少 {missing}，多出 {extra}")
        for code, industry in industries.items():
            unknown = sorted((set(industry.params) | set(industry.derived)) - set(ALL_KEYS))
            if unknown:
                raise ValueError(f"defaults.yaml 中业态 {code} 有未知参数：{unknown}")
        if set(industries) != set(checks):
            raise ValueError("defaults.yaml 与 checks.yaml 的业态列表不一致")

        self.key = key
        self.specs = {s.key: s for s in specs}
        self._industries = industries
        self._checks = checks

    @property
    def industry_codes(self) -> list[str]:
        return list(self._industries)

    @property
    def quick_required_keys(self) -> list[str]:
        return [k for k, s in self.specs.items() if s.quick_required]

    def industry(self, code: str) -> IndustryDefaults:
        if code not in self._industries:
            raise KeyError(f"未知业态：{code}，可选：{'、'.join(self._industries)}")
        return self._industries[code]

    def check_rules(self, code: str) -> CheckRules:
        self.industry(code)
        return self._checks[code]

    def traffic_defaults(self, code: str) -> TrafficDefaults:
        return self.industry(code).traffic

    def quick_missing(self, params: PhysicalStoreParams) -> list[str]:
        """快速测算的最少必填项中，还没有填写的参数。"""
        return [k for k in self.quick_required_keys if params.get(k) is None]

    def fill_defaults(
        self, params: PhysicalStoreParams, industry: str, today: date | None = None
    ) -> tuple[PhysicalStoreParams, list[str]]:
        """给缺失的测算参数补上业态默认值，返回 (新参数, 补了哪些参数)。

        已经填写的参数不会被覆盖。没有默认值的参数（如客单价）保持缺失。
        """
        config = self.industry(industry)
        changes: dict[str, dict[str, Any]] = {}

        for key in params.missing_keys():
            note = config.notes.get(key)
            if key in config.params:
                raw = config.params[key]
                value = dict(raw) if isinstance(raw, dict) and "base" in raw else {"base": raw}
                note = note or f"{config.label}常见水平（默认值，待核实）"
            elif key in config.derived:
                rule = config.derived[key]
                reference = params.get(rule.ratio_of)
                if reference is None:
                    continue
                value = {"base": round(reference.base * rule.ratio, 2)}
                label = self.specs[rule.ratio_of].label
                note = note or f"按{label}的 {rule.ratio:.0%} 估算（{config.label}默认值，待核实）"
            elif key == "revenue.opening_month":
                current = (today or date.today()).month
                value = {"base": (current + 1) % 12 + 1}
                note = note or "按当前日期推后两个月估算"
            else:
                continue
            changes[key] = {**value, "source": "default", "note": note}

        if not changes:
            return params, []
        return params.with_values(changes), list(changes)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


@lru_cache
def load_template(key: str = "physical_store") -> Template:
    """读取模板配置。结果会被缓存，修改 YAML 后需要重启程序。"""
    folder = TEMPLATES_DIR / key
    specs = [
        ParamSpec.model_validate(item)
        for item in _read_yaml(folder / "parameters.yaml")["parameters"]
    ]
    industries = {
        code: IndustryDefaults.model_validate(item)
        for code, item in _read_yaml(folder / "defaults.yaml")["industries"].items()
    }
    checks = {
        code: CheckRules.model_validate(item)
        for code, item in _read_yaml(folder / "checks.yaml")["industries"].items()
    }
    return Template(key, specs, industries, checks)
