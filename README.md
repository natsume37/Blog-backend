# Blog Backend

FastAPI backend for the Miyazaki Style Blog.

## Tech Stack

- **Framework**: FastAPI
- **Database**: MySQL
- **ORM**: SQLAlchemy
- **Package Manager**: uv

## Setup

### 1. Install uv (if not installed)

```bash
pip install uv
```

### 2. Create virtual environment and install dependencies

```bash
cd backend
uv sync
```

### 3. Create MySQL database

```sql
CREATE DATABASE blog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Configure environment (uv + env files)

This project reads config by `ENVIRONMENT`:

- `development` -> `.env.dev`
- `production` -> `.env.prod`
- `staging` -> `.env.staging`

Create your env files from templates:

```bash
cp .env.dev.example .env.dev
cp .env.prod.example .env.prod
```

Important production fields:

- `SECRET_KEY`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL`

### 5. Create Admin Account

```bash
# Use default admin (admin / admin123)
uv run python scripts/create_admin.py

# Or use interactive mode
uv run python scripts/create_admin.py -i

# Or specify parameters
uv run python scripts/create_admin.py -u myusername -e myemail@example.com -p mypassword -n "My Nickname"
```

### 6. Run with uv

Use the helper script (recommended):

```bash
# development (reload on)
./scripts/uv-run.sh dev

# production (reload off)
./scripts/uv-run.sh prod
```

Or run directly:

```bash
ENVIRONMENT=development uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
ENVIRONMENT=production uv run uvicorn app.main:app --host 0.0.0.0 --port 8090
```

### 7. systemd (production)

Use `EnvironmentFile` so backend env is managed in one place:

```ini
[Unit]
Description=FastAPI Blog Backend
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/work/blog/Blog-backend
EnvironmentFile=/root/work/blog/Blog-backend/.env.prod
Environment=ENVIRONMENT=production
ExecStart=/usr/local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8090
Restart=always

[Install]
WantedBy=multi-user.target
```

Tip: use `which uv` on server and replace `/usr/local/bin/uv` if your path differs.

## API Documentation

Once the server is running, visit:

- Swagger UI: http://localhost:8090/docs
- ReDoc: http://localhost:8090/redoc

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # Application entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # Configuration settings
│   │   ├── database.py      # Database connection
│   │   ├── deps.py          # Dependency injection (auth)
│   │   └── security.py      # JWT & password hashing
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User model
│   │   ├── article.py       # Article, Category, Tag models
│   │   ├── message.py       # Message, Comment models
│   │   └── site.py          # Site info model
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication routes
│   │   ├── articles.py      # Article routes
│   │   ├── categories.py    # Category & Tag routes
│   │   ├── messages.py      # Message routes
│   │   └── site.py          # Site info routes
│   └── schemas/
│       ├── __init__.py
│       ├── common.py        # Common response models
│       ├── user.py          # User schemas
│       ├── article.py       # Article schemas
│       ├── message.py       # Message schemas
│       └── site.py          # Site schemas
├── scripts/
│   └── create_admin.py      # Admin creation script
├── pyproject.toml           # Project dependencies
└── README.md
```

## Database Migrations (Alembic)

This project uses Alembic for database migrations.

### Initialize (Already done)

```bash
uv run alembic init alembic
```

### Generate a new migration

After modifying `app/models/*.py`:

```bash
uv run alembic revision --autogenerate -m "Description of changes"
```

### Apply migrations

To upgrade the database to the latest version:

```bash
uv run alembic upgrade head
```

### Downgrade

To undo the last migration:

```bash
uv run alembic downgrade -1
```
