# 商业罗盘

帮助个人创业者和小店主判断商业模式是否可行，并辅助获客与运营。

设计文档在 [`docs/`](docs/) 目录，建议从 [产品规划](docs/产品规划.md) 开始看。

下一阶段的实施顺序、验收标准和当前验证情况见 [开发计划](docs/开发计划.md)。

## 当前进度

- [x] 计算引擎（`backend/app/engine/`）：实体小店测算，纯计算，不依赖数据库和 AI
- [x] 模板配置（`backend/app/templates/`）：饮品业态的问法、默认值、经验阈值（数值为占位，待核实）
- [x] 项目骨架：Docker Compose、FastAPI、PostgreSQL、邮箱注册登录
- [ ] AI 访谈
- [x] 前端骨架（`frontend/`）：登录注册、验证邮箱、重置密码、我的、协议页；手机和桌面两套布局
- [x] 档案、参数编辑、历史测算、现金曲线与临时试算页面
- [ ] AI 访谈页面
- [ ] 内容生成

## 用 Docker 启动

```bash
cp .env.example .env      # 第一次：复制配置模板，填写密码和密钥
docker compose up -d --build
```

启动后访问：

| 地址 | 内容 |
|---|---|
| http://localhost:8080 | 网站 |
| http://localhost:8080/api/docs | 接口文档（生产环境自动关闭） |
| http://localhost:8080/api/health | 健康检查 |

常用命令：

```bash
docker compose ps                 # 查看状态
docker compose logs -f api        # 查看后端日志
docker compose down               # 停止（数据保留在 pgdata 数据卷里）
docker compose up -d --build nginx  # 改了前端代码后，重新打包并发布网页
```

## 前端开发

需要 Node 22。本机用 nvm 安装，新开的终端默认仍是系统自带的 Node，进入 `frontend` 后用 `nvm use` 切换（只影响当前终端）。

```bash
cd frontend
nvm use              # 按 .nvmrc 切换到 Node 22
npm install          # 第一次运行：安装依赖
npm run dev          # 开发服务器 http://localhost:5173，改代码页面立刻刷新；/api 请求转发到 Docker 里的后端
npm test             # 单元测试
npm run typecheck    # 类型检查
npm run gen:api      # 后端接口改了以后，重新生成前端的接口类型（需要后端在运行）
```

开发服务器需要后端在运行（`docker compose up -d`）。

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
  app/profiles/       档案、参数、修改记录
  app/evaluations/    不可变快照与临时试算
  app/mail/           邮件发送
  app/db/             数据库表定义和迁移
  tests/              测试
frontend/             前端网页（Vue 3 + Vant）
deploy/nginx/         Nginx 配置
compose.yaml          Docker Compose
```
