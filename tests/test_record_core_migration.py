"""验证公共记录核心迁移的升级、回填和降级路径。"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[1] / "alembic/versions/7b3e91c4a2d8_add_modular_record_core.py"
    spec = importlib.util.spec_from_file_location("record_core_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载记录核心迁移")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_core_migration_backfills_legacy_records() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                is_admin BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE book_records (
                id INTEGER PRIMARY KEY,
                source VARCHAR(30), source_id VARCHAR(80), title VARCHAR(255),
                author VARCHAR(255), status VARCHAR(30), progress INTEGER,
                read_seconds INTEGER, note_summary TEXT, tags_json TEXT,
                visibility VARCHAR(20), is_in_shelf BOOLEAN,
                last_read_at DATETIME, finished_at DATETIME,
                created_at DATETIME, updated_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE movie_records (
                id INTEGER PRIMARY KEY,
                source VARCHAR(30), source_id VARCHAR(80), title VARCHAR(255),
                director VARCHAR(255), status VARCHAR(30), note TEXT,
                tags_json TEXT, visibility VARCHAR(20), watched_at DATETIME,
                created_at DATETIME, updated_at DATETIME
            )
            """
        )
        connection.exec_driver_sql("INSERT INTO users (id, is_admin) VALUES (1, 1)")
        connection.exec_driver_sql(
            """INSERT INTO book_records
            (id, source, source_id, title, author, status, progress, read_seconds,
             note_summary, tags_json, visibility, is_in_shelf, last_read_at)
            VALUES (1, 'weread', 'book-1', '设计基础', '作者', '阅读中', 30, 600,
                    '一句笔记', '[\"设计\", \"阅读\"]', 'public', 1, '2026-08-01 10:00:00')"""
        )
        connection.exec_driver_sql(
            """INSERT INTO movie_records
            (id, source, source_id, title, director, status, note,
             tags_json, visibility, watched_at)
            VALUES (1, 'manual', 'movie-1', '银翼杀手', '导演', '已看完', '一句观后感',
                    '[\"设计\"]', 'private', '2026-08-01 11:00:00')"""
        )

        migration = _migration_module()
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        migration.op = operations
        migration.upgrade()

        entries = connection.execute(sa.text("SELECT kind, title FROM record_entries ORDER BY id")).all()
        tags = connection.execute(sa.text("SELECT name FROM record_tags ORDER BY id")).scalars().all()
        links = connection.execute(sa.text("SELECT COUNT(*) FROM record_entry_tags")).scalar_one()
        assert entries == [("reading", "设计基础"), ("movie", "银翼杀手")]
        assert tags == ["设计", "阅读"]
        assert links == 3

        migration.downgrade()
        remaining = sa.inspect(connection).get_table_names()
        assert "record_entries" not in remaining
        assert "note_records" not in remaining
        assert "focus_sessions" not in remaining
