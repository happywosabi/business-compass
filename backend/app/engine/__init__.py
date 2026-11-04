"""计算引擎：纯计算，不读文件、不连数据库、不调用 AI、不访问网络。

对外入口：
- evaluate         完整评估
- what_if          假设性测算（不保存）
- estimate_traffic 客流估算
"""

from .checks import CheckRules
from .evaluate import evaluate, what_if
from .params import MissingParametersError, ParamValue, PhysicalStoreParams
from .results import EvaluationResult, WhatIfResult
from .traffic import TrafficDefaults, TrafficEstimate, estimate_traffic
from .version import ENGINE_VERSION

__all__ = [
    "ENGINE_VERSION",
    "CheckRules",
    "EvaluationResult",
    "MissingParametersError",
    "ParamValue",
    "PhysicalStoreParams",
    "TrafficDefaults",
    "TrafficEstimate",
    "WhatIfResult",
    "estimate_traffic",
    "evaluate",
    "what_if",
]
