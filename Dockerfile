# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /build

# 使用 uv 锁定生产依赖，保证本地、CI 与服务器使用同一套环境。
RUN pip install --no-cache-dir uv==0.11.26

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app

COPY --from=builder --chown=app:app /build/.venv /app/.venv
COPY --from=builder --chown=app:app /build/app /app/app
COPY --from=builder --chown=app:app /build/alembic /app/alembic
COPY --from=builder --chown=app:app /build/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /build/pyproject.toml /app/pyproject.toml
COPY --from=builder --chown=app:app /build/uv.lock /app/uv.lock

RUN mkdir -p /app/logs && chown app:app /app/logs

USER app

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/docs', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
