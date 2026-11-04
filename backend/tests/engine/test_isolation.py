"""计算引擎只做计算：不允许引用 app 下的其他模块，也不允许引用读写文件、数据库、网络、AI 相关的库。"""

import ast
from pathlib import Path

import app.engine

ENGINE_DIR = Path(app.engine.__file__).parent
FORBIDDEN = {
    "yaml",
    "sqlalchemy",
    "psycopg",
    "asyncpg",
    "fastapi",
    "httpx",
    "requests",
    "openai",
    "socket",
    "urllib",
}


def _imported_modules(source: str) -> list[str]:
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def test_engine_has_no_outside_dependencies():
    files = sorted(ENGINE_DIR.glob("*.py"))
    assert files
    for file in files:
        for module in _imported_modules(file.read_text(encoding="utf-8")):
            top = module.split(".")[0]
            assert top not in FORBIDDEN, f"{file.name} 引用了 {module}"
            if top == "app":
                assert module.startswith("app.engine"), f"{file.name} 引用了 {module}"
