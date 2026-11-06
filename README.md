# 商业罗盘

帮助个人创业者、小店主和在产果农判断商业模式是否可行，并辅助获客与运营。

设计文档在 [`docs/`](docs/) 目录，建议从 [产品规划](docs/产品规划.md) 开始看。

下一阶段的实施顺序、验收标准和当前验证情况见 [开发计划](docs/开发计划.md)。

## 当前进度

- [x] 计算引擎（`backend/app/engine/`）：实体小店测算，纯计算，不依赖数据库和 AI
- [x] 模板配置（`backend/app/templates/`）：饮品业态的问法、默认值、经验阈值（数值为占位，待核实）
- [x] 项目骨架：Docker Compose、FastAPI、PostgreSQL、邮箱注册登录
- [x] AI 访谈后端：工具调用、消息持久化、配额、幂等与恢复
- [x] 前端骨架（`frontend/`）：登录注册、验证邮箱、重置密码、我的、协议页；手机和桌面两套布局
- [x] 档案、参数编辑、历史测算、现金曲线与临时试算页面
- [x] AI 访谈页面、结果解读（数字核对失败时降级）
- [x] 内容生成：日历/门店选题、朋友圈/小红书草稿与来源记录
- [x] 后台任务：到期档案清理、可选热点采集
- [x] 果园经营档案：多品种/等级/批零渠道、经营期总账、家庭劳动估值、历史试算和供货文案；[模型说明](docs/果园经营测算模型.md)
- [ ] 公开上线验收：默认值来源、运营主体、HTTPS与真实手机/微信

## 用 Docker 启动

```bash
cp .env.example .env      # 第一次：复制配置模板，填写密码和密钥
docker compose up -d --build
```

启动后访问：

默认HTTP仅绑定本机。公网部署使用 [HTTPS生产配置](docs/部署与验收.md#https)，不要直接公开开发入口。

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
  app/interview/      AI访谈、工具调用、SSE
  app/llm/            模型适配、配额、报告核对
  app/content/        选题、草稿与可选热点
  app/worker.py       到期档案清理与热点采集
  app/mail/           邮件发送
  app/db/             数据库表定义和迁移
  tests/              测试
frontend/             前端网页（Vue 3 + Vant）
deploy/nginx/         Nginx 配置
compose.yaml          Docker Compose
```


## AI 与内容配置

配置 `.env` 中的 `DEEPSEEK_API_KEY`、`INTERVIEW_MODEL` 和 `REPORT_MODEL`；AI 功能需要已验证邮箱，手工参数编辑和测算不依赖 AI。模型名以账号 `/models` 返回为准。

访谈断线后可恢复持久化历史，运行中的请求可取消。幂等编号防止同次请求重复写入；服务重启后中断的任务会到期失败，已保存参数保留。API 当前按单进程部署，后台任务不自动重放。

每个账号最多同时运行3个AI任务，报告和文案可以并行；同一档案的访谈按顺序处理。新档案默认进入AI访谈，可点“手动填写”。确认测算后直接打开结果页；参数未变时复用原快照及报告，离开或刷新可继续查看生成状态。

访谈使用 `record_periodic_value` 由代码换算日/月/年单位，日薪和月销量需先确认工作/营业天数。亲属报酬与老板工资分别记录。文案提示词见 `backend/app/content/prompt.md`：小红书采用标题、短段、适量emoji和话题；关键信息缺失时保留最多3个 `【待填：…】`，在页面填入或删行后复制。

内容页在 `/content`。默认由 worker 每两小时读取固定的中新网/食品伙伴网公开 RSS，筛选近期行业资讯；可用 `HOTAPI_BASE_URL` 叠加运维配置的自部署 DailyHotApi。来源失败不影响日历和日常选题。采集遵守公共预算，页面刷新只读缓存，后台展示来源诊断；详情见[热点关联与联网检索](docs/热点关联与联网检索.md)。

## 备份与恢复验证

```bash
deploy/scripts/backup.sh /安全目录/business-compass.dump
deploy/scripts/verify-backup.sh /安全目录/business-compass.dump
```

验证脚本只恢复到临时数据库并自动删除它，不修改在线库。备份包含用户数据，应限制读取权限并按保留策略存储。上线细节和当前限制见 [部署与验收](docs/部署与验收.md)。

GitHub Actions 配置暂以 [CI模板](deploy/ci/checks.yml) 交付；当前凭据缺少 `workflow` 权限，取得权限后移至 `.github/workflows/checks.yml` 启用。

- 水果零售店：实体小店内选择“水果店（零售）”，支持两种采购成本口径、损耗、库存占用、筹备/经营中预测和水果文案；见[测算模型](docs/水果零售店测算模型.md)。
