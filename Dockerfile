# ------------------------------------------------------------------------------
# atengk-mcp-server-rdbms: 官方容器化部署镜像
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_RDBMS_TRANSPORT=sse \
    MCP_RDBMS_SERVER_HOST=0.0.0.0 \
    MCP_RDBMS_SERVER_PORT=8000

# 安装系统基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 从官方 uv 镜像复制极速包管理器
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 拷贝代码与依赖文件
COPY pyproject.toml README.md ./
COPY src/ ./src/

# 安装服务及其常用数据库驱动
RUN uv pip install --system --no-cache ".[all]" || uv pip install --system --no-cache .

# 暴露 SSE 传输端口
EXPOSE 8000

# 容器启动入口（支持无参启动）
ENTRYPOINT ["atengk-mcp-server-rdbms"]
