"""Copy the current Blog data set from MySQL into PostgreSQL.

The historical Alembic chain contains MySQL-specific operations, so the first
PostgreSQL cutover builds schema from the current SQLAlchemy models and then
stamps the target database with the current Alembic head.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.schema import Table

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.database import Base  # noqa: E402
from app import models  # noqa: F401,E402  # import registers metadata


def _masked(url: str) -> str:
    return make_url(url).render_as_string(hide_password=True)


def _require_backend(url: str, expected: str, role: str) -> None:
    backend = make_url(url).get_backend_name()
    if backend != expected:
        raise ValueError(f"{role} URL must use {expected}, got {backend}")


def _engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def _current_alembic_head() -> str:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    if not head:
        raise RuntimeError("Unable to resolve Alembic head revision")
    return head


def _count(conn: Connection, table: Table) -> int:
    return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def _ordered_select(table: Table):
    statement = select(table)
    if table.primary_key.columns:
        statement = statement.order_by(*table.primary_key.columns)
    return statement


def _copy_table(source: Connection, target: Connection, table: Table, batch_size: int) -> tuple[int, int]:
    source_count = _count(source, table)
    copied = 0
    result = source.execution_options(stream_results=True).execute(_ordered_select(table))

    while rows := result.fetchmany(batch_size):
        payload = [dict(row._mapping) for row in rows]
        target.execute(insert(table), payload)
        copied += len(payload)

    return source_count, copied


def _reset_postgres_sequences(target: Connection) -> None:
    for table in Base.metadata.sorted_tables:
        for column in table.primary_key.columns:
            if not getattr(column, "autoincrement", False):
                continue
            sequence = target.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            ).scalar()
            if not sequence:
                continue

            max_value = target.execute(select(func.max(column)).select_from(table)).scalar() or 0
            if max_value:
                target.execute(
                    text("SELECT setval(CAST(:sequence AS regclass), :value, true)"),
                    {"sequence": sequence, "value": int(max_value)},
                )
            else:
                target.execute(
                    text("SELECT setval(CAST(:sequence AS regclass), 1, false)"),
                    {"sequence": sequence},
                )


def _stamp_alembic_head(target: Connection, revision: str) -> None:
    target.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
    target.execute(text("DELETE FROM alembic_version"))
    target.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"), {"revision": revision})


def migrate(source_url: str, target_url: str, drop_target: bool, batch_size: int) -> None:
    _require_backend(source_url, "mysql", "source")
    _require_backend(target_url, "postgresql", "target")

    source_engine = _engine(source_url)
    target_engine = _engine(target_url)
    revision = _current_alembic_head()

    print(f"source={_masked(source_url)}")
    print(f"target={_masked(target_url)}")
    print(f"alembic_head={revision}")

    if drop_target:
        with target_engine.begin() as target:
            target.execute(text("DROP TABLE IF EXISTS alembic_version"))
        Base.metadata.drop_all(target_engine)

    Base.metadata.create_all(target_engine)

    copied_counts: dict[str, tuple[int, int]] = {}
    with source_engine.connect() as source, target_engine.begin() as target:
        for table in Base.metadata.sorted_tables:
            source_count, copied = _copy_table(source, target, table, batch_size)
            copied_counts[table.name] = (source_count, copied)
            print(f"{table.name}: source={source_count} copied={copied}")

        _reset_postgres_sequences(target)
        _stamp_alembic_head(target, revision)

    with target_engine.connect() as target:
        mismatches: list[str] = []
        for table in Base.metadata.sorted_tables:
            source_count, copied = copied_counts[table.name]
            target_count = _count(target, table)
            if source_count != copied or source_count != target_count:
                mismatches.append(
                    f"{table.name}: source={source_count}, copied={copied}, target={target_count}"
                )
        stamped = target.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if stamped != revision:
            mismatches.append(f"alembic_version: expected={revision}, actual={stamped}")

    if mismatches:
        print("verification_failed")
        for mismatch in mismatches:
            print(mismatch)
        raise SystemExit(1)

    print("verification_ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Blog data from MySQL to PostgreSQL.")
    parser.add_argument("--source-url", default=os.getenv("MYSQL_DATABASE_URL"), help="Source MySQL SQLAlchemy URL")
    parser.add_argument("--target-url", default=os.getenv("POSTGRES_DATABASE_URL"), help="Target PostgreSQL SQLAlchemy URL")
    parser.add_argument("--drop-target", action="store_true", help="Drop known target tables before copying")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows inserted per batch")
    args = parser.parse_args()

    if not args.source_url:
        raise SystemExit("MYSQL_DATABASE_URL or --source-url is required")
    if not args.target_url:
        raise SystemExit("POSTGRES_DATABASE_URL or --target-url is required")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")

    migrate(args.source_url, args.target_url, args.drop_target, args.batch_size)


if __name__ == "__main__":
    main()
