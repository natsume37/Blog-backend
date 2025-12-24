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

### 4. Configure database

The default configuration is:

- Host: localhost
- Port: 3306
- User: root
- Password: 123
- Database: blog

You can override these by creating a `.env` file:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123
DB_NAME=blog
SECRET_KEY=your-secret-key-here
```

### 5. Create Admin Account

```bash
# Use default admin (admin / admin123)
uv run python scripts/create_admin.py

# Or use interactive mode
uv run python scripts/create_admin.py -i

# Or specify parameters
uv run python scripts/create_admin.py -u myusername -e myemail@example.com -p mypassword -n "My Nickname"
```

### 6. Run the server

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

# Or if uv command has issues, use venv directly:

```bash
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate # Linux/Mac
python -m uvicorn app.main:app --reload
```

## API Documentation

Once the server is running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

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
