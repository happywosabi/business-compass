# 商业罗盘

帮助个人创业者和小店主判断商业模式是否可行，并辅助获客与运营。

设计文档在 [`docs/`](docs/) 目录，建议从 [产品规划](docs/产品规划.md) 开始看。

## 当前进度

- [x] 计算引擎（`backend/app/engine/`）：实体小店测算，纯计算，不依赖数据库和 AI
- [x] 模板配置（`backend/app/templates/`）：饮品业态的问法、默认值、经验阈值（数值为占位，待核实）
- [x] 项目骨架：Docker Compose、FastAPI、PostgreSQL、邮箱注册登录
- [ ] AI 访谈
- [ ] 手机网页（目前是临时测试页）
- [ ] 内容生成

## 用 Docker 启动

```bash
cp .env.example .env      # 第一次：复制配置模板，填写密码和密钥
docker compose up -d --build
```

启动后访问：

| 地址 | 内容 |
|---|---|
| http://localhost:8080 | 临时测试页：注册、登录 |
| http://localhost:8080/api/docs | 接口文档（生产环境自动关闭） |
| http://localhost:8080/api/health | 健康检查 |

常用命令：

```bash
docker compose ps                 # 查看状态
docker compose logs -f api        # 查看后端日志
docker compose down               # 停止（数据保留在 pgdata 数据卷里）
```

## 运行测试

需要先安装 [uv](https://docs.astral.sh/uv/)。接口测试需要数据库，先用 `docker compose up -d db` 启动；
没有数据库时接口测试会被跳过，计算引擎等其他测试照常运行。

```bash
cd backend
uv sync                 # 第一次运行：安装 Python 3.12 和依赖
uv run pytest           # 运行全部测试（测试不会真正发送邮件）
uv run ruff check .     # 代码检查
uv run ruff format .    # 代码格式化
```

> 如果终端里加载了 ROS 环境（`PYTHONPATH` 指向 `/opt/ros/...`），ROS 的 pytest 插件会干扰测试。
> 运行前去掉这个环境变量即可：`env -u PYTHONPATH uv run pytest`

修改数据库表结构（`backend/app/db/models.py`）后，生成迁移文件：

```bash
cd backend
uv run alembic revision --autogenerate -m "说明"
```

容器启动时会自动执行 `alembic upgrade head`，把数据库升级到最新结构。

## 目录

```
docs/                 设计文档
backend/
  app/engine/         计算引擎
  app/templates/      模板配置（YAML）
  app/auth/           注册、登录、会话
  app/mail/           邮件发送
  app/db/             数据库表定义和迁移
  tests/              测试
deploy/nginx/         Nginx 配置和临时测试页
compose.yaml          Docker Compose
```
