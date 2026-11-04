# 后端镜像：FastAPI + 计算引擎
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# 安装 uv（依赖管理工具）。下载慢时可以在构建时指定镜像源，例如：
#   docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" uv==0.11.16

WORKDIR /app

# 先只复制依赖清单并安装依赖：代码变动时可以复用这一层缓存，构建更快
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY app ./app

# 不用 root 用户运行
RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000

# 启动时先把数据库升级到最新结构，再启动服务
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
