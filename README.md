# 商业罗盘

帮助个人创业者和小店主判断商业模式是否可行，并辅助获客与运营。

设计文档在 [`docs/`](docs/) 目录，建议从 [产品规划](docs/产品规划.md) 开始看。

## 当前进度

- [x] 计算引擎（`backend/app/engine/`）：实体小店测算，纯计算，不依赖数据库和 AI
- [x] 模板配置（`backend/app/templates/`）：饮品业态的问法、默认值、经验阈值（数值为占位，待核实）
- [ ] 项目骨架：Docker Compose、FastAPI、PostgreSQL、登录
- [ ] AI 访谈
- [ ] 手机网页
- [ ] 内容生成

## 运行测试

需要先安装 [uv](https://docs.astral.sh/uv/)。

```bash
cd backend
uv sync                 # 第一次运行：安装 Python 3.12 和依赖
uv run pytest           # 运行全部测试
uv run ruff check .     # 代码检查
uv run ruff format .    # 代码格式化
```

> 如果终端里加载了 ROS 环境（`PYTHONPATH` 指向 `/opt/ros/...`），ROS 的 pytest 插件会干扰测试。
> 运行前去掉这个环境变量即可：`env -u PYTHONPATH uv run pytest`

## 目录

```
docs/                 设计文档
backend/
  app/engine/         计算引擎
  app/templates/      模板配置（YAML）
  tests/              测试
```
