"""为全新 PostgreSQL 创建当前完整结构并写入 Alembic head。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, MetaData, inspect, text


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models  # noqa: E402,F401  # 导入全部模型，注册 Base.metadata
from app.core.database import Base, engine  # noqa: E402


def current_revision(db_engine: Engine) -> str | None:
    """返回当前 Alembic 版本；未建版本表或版本表为空时返回 None。"""
    if "alembic_version" not in inspect(db_engine).get_table_names():
        return None

    with db_engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def bootstrap_database(
    db_engine: Engine,
    metadata: MetaData,
    stamp_head: Callable[[], None],
) -> bool:
    """只初始化空库，或恢复已完整建表但尚未 stamp 的引导过程。"""
    revision = current_revision(db_engine)
    if revision:
        print(f"database already versioned at {revision}; skipping bootstrap")
        return False

    existing_tables = set(inspect(db_engine).get_table_names()) - {"alembic_version"}
    expected_tables = {table.name for table in metadata.sorted_tables}

    if existing_tables and existing_tables != expected_tables:
        missing = sorted(expected_tables - existing_tables)
        extra = sorted(existing_tables - expected_tables)
        raise RuntimeError(
            "refusing to stamp an unversioned, non-empty database; "
            f"missing_tables={missing}, extra_tables={extra}"
        )

    if not existing_tables:
        print("empty database detected; creating current SQLAlchemy schema")
        metadata.create_all(bind=db_engine)
    else:
        print("complete unversioned schema detected; resuming bootstrap stamp")

    stamp_head()
    return True


def main() -> None:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    head_revision = ScriptDirectory.from_config(config).get_current_head()
    if not head_revision:
        raise RuntimeError("unable to resolve Alembic head")

    initialized = bootstrap_database(
        engine,
        Base.metadata,
        lambda: command.stamp(config, "head"),
    )
    actual_revision = current_revision(engine)
    if actual_revision != head_revision:
        raise RuntimeError(
            f"Alembic revision verification failed: expected={head_revision}, actual={actual_revision}"
        )

    result = "initialized" if initialized else "already versioned"
    print(f"database bootstrap verified: {result}, revision={actual_revision}")


if __name__ == "__main__":
    main()
