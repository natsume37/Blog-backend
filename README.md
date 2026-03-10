# Blog Backend

[中文（默认）](./README.md) | [English](./README.en.md)

FastAPI 博客后端服务。

## 技术栈

- **框架**: FastAPI
- **数据库**: MySQL
- **ORM**: SQLAlchemy
- **包管理器**: uv

## 快速开始

### 1. 安装 uv（若未安装）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 安装并固定 Python 版本

```bash
uv python install 3.11
uv python pin 3.11
```

### 3. 创建虚拟环境并安装依赖

```bash
uv sync
```

`uv sync` 会按 `.python-version` 创建本地 `.venv`，并优先使用 `uv.lock` 还原环境。

### 4. 创建 MySQL 数据库

```sql
CREATE DATABASE blog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 配置环境变量

项目根据 `ENVIRONMENT` 读取配置文件：

- `development` -> `.env.dev`
- `production` -> `.env.prod`
- `staging` -> `.env.staging`

从模板复制：

```bash
cp .env.dev.example .env.dev
cp .env.prod.example .env.prod
```

生产环境重点配置项：

- `SECRET_KEY`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL`

### 6. 创建管理员账号

```bash
# 使用默认账号（admin / admin123）
uv run python scripts/create_admin.py

# 交互模式
uv run python scripts/create_admin.py -i

# 指定参数
uv run python scripts/create_admin.py -u myusername -e myemail@example.com -p mypassword -n "My Nickname"
```

### 7. 启动服务

推荐使用脚本：

```bash
# 开发环境（开启热重载）
./scripts/uv-run.sh dev

# 生产环境（关闭热重载）
./scripts/uv-run.sh prod
```

或直接执行：

```bash
ENVIRONMENT=development uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
ENVIRONMENT=production uv run uvicorn app.main:app --host 0.0.0.0 --port 8090
```

## API 文档

服务启动后可访问：

- Swagger UI: http://localhost:8090/docs
- ReDoc: http://localhost:8090/redoc

## 数据库迁移（Alembic）

```bash
# 生成迁移（模型变更后）
uv run alembic revision --autogenerate -m "Description of changes"

# 执行迁移
uv run alembic upgrade head

# 回滚最近一次迁移
uv run alembic downgrade -1
```

## 项目结构

```text
Blog-backend/
├── app/
├── alembic/
├── scripts/
├── pyproject.toml
└── README.md
```
