"""add modular record core

Revision ID: 7b3e91c4a2d8
Revises: d2e4f6a8b0c1
Create Date: 2026-08-01 07:10:00.000000
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b3e91c4a2d8"
down_revision: Union[str, None] = "d2e4f6a8b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


migration_metadata = sa.MetaData()
record_entries = sa.Table(
    "record_entries",
    migration_metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("owner_id", sa.Integer()),
    sa.Column("kind", sa.String(length=30)),
    sa.Column("title", sa.String(length=255)),
    sa.Column("summary", sa.Text()),
    sa.Column("visibility", sa.String(length=20)),
    sa.Column("status", sa.String(length=30)),
    sa.Column("occurred_at", sa.DateTime()),
    sa.Column("source", sa.String(length=30)),
    sa.Column("source_key", sa.String(length=120)),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("updated_at", sa.DateTime()),
)
record_tags = sa.Table(
    "record_tags",
    migration_metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("owner_id", sa.Integer()),
    sa.Column("name", sa.String(length=80)),
    sa.Column("slug", sa.String(length=100)),
    sa.Column("color", sa.String(length=20)),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("updated_at", sa.DateTime()),
)
record_entry_tags = sa.Table(
    "record_entry_tags",
    migration_metadata,
    sa.Column("record_id", sa.Integer(), primary_key=True),
    sa.Column("tag_id", sa.Integer(), primary_key=True),
)
book_records = sa.Table(
    "book_records",
    migration_metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("source", sa.String(length=30)),
    sa.Column("source_id", sa.String(length=80)),
    sa.Column("title", sa.String(length=255)),
    sa.Column("author", sa.String(length=255)),
    sa.Column("status", sa.String(length=30)),
    sa.Column("progress", sa.Integer()),
    sa.Column("read_seconds", sa.Integer()),
    sa.Column("note_summary", sa.Text()),
    sa.Column("tags_json", sa.Text()),
    sa.Column("visibility", sa.String(length=20)),
    sa.Column("is_in_shelf", sa.Boolean()),
    sa.Column("last_read_at", sa.DateTime()),
    sa.Column("finished_at", sa.DateTime()),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("updated_at", sa.DateTime()),
    sa.Column("record_entry_id", sa.Integer()),
)
movie_records = sa.Table(
    "movie_records",
    migration_metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("source", sa.String(length=30)),
    sa.Column("source_id", sa.String(length=80)),
    sa.Column("title", sa.String(length=255)),
    sa.Column("director", sa.String(length=255)),
    sa.Column("status", sa.String(length=30)),
    sa.Column("note", sa.Text()),
    sa.Column("tags_json", sa.Text()),
    sa.Column("visibility", sa.String(length=20)),
    sa.Column("watched_at", sa.DateTime()),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("updated_at", sa.DateTime()),
    sa.Column("record_entry_id", sa.Integer()),
)


def _now() -> datetime:
    """统一使用无时区 UTC，兼容现有 DateTime 字段。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _first_owner_id(connection: sa.Connection) -> int | None:
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("is_admin", sa.Boolean),
    )
    return connection.execute(
        sa.select(users.c.id)
        .where(users.c.is_admin.is_(True))
        .order_by(users.c.id.asc())
        .limit(1)
    ).scalar()


def _normalize_visibility(value: Any) -> str:
    return "public" if str(value or "").strip().lower() == "public" else "private"


def _parse_tags(raw: Any) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        name = str(item).strip()
        key = name.casefold()
        if name and key not in seen:
            result.append(name[:80])
            seen.add(key)
    return result


def _tag_slug(name: str) -> str:
    slug = re.sub(r"\s+", "-", name.strip().casefold())
    return slug[:100] or "tag"


def _record_time(*values: Any) -> datetime:
    for value in values:
        if isinstance(value, datetime):
            return value
    return _now()


def _insert_tag(
    connection: sa.Connection,
    cache: dict[tuple[int | None, str], int],
    *,
    owner_id: int | None,
    name: str,
    now: datetime,
) -> int:
    cache_key = (owner_id, name.casefold())
    existing = cache.get(cache_key)
    if existing is not None:
        return existing

    result = connection.execute(
        record_tags.insert().values(
            owner_id=owner_id,
            name=name,
            slug=_tag_slug(name),
            color="#8ca093",
            created_at=now,
            updated_at=now,
        )
    )
    tag_id = result.inserted_primary_key[0]
    if tag_id is None:
        tag_id = connection.execute(
            sa.select(record_tags.c.id)
            .where(record_tags.c.owner_id == owner_id)
            .where(record_tags.c.name == name)
            .order_by(record_tags.c.id.desc())
            .limit(1)
        ).scalar_one()
    cache[cache_key] = int(tag_id)
    return int(tag_id)


def _insert_entry(
    connection: sa.Connection,
    *,
    owner_id: int | None,
    kind: str,
    source: str,
    source_key: str,
    title: str,
    summary: str,
    visibility: str,
    occurred_at: datetime,
    created_at: datetime,
    updated_at: datetime,
) -> int:
    result = connection.execute(
        record_entries.insert().values(
            owner_id=owner_id,
            kind=kind,
            title=title[:255],
            summary=summary,
            visibility=visibility,
            status="active",
            occurred_at=occurred_at,
            source=source[:30],
            source_key=source_key[:120],
            created_at=created_at,
            updated_at=updated_at,
        )
    )
    entry_id = result.inserted_primary_key[0]
    if entry_id is None:
        entry_id = connection.execute(
            sa.select(record_entries.c.id)
            .where(record_entries.c.kind == kind)
            .where(record_entries.c.source == source)
            .where(record_entries.c.source_key == source_key)
            .limit(1)
        ).scalar_one()
    return int(entry_id)


def _link_tags(
    connection: sa.Connection,
    cache: dict[tuple[int | None, str], int],
    *,
    record_id: int,
    owner_id: int | None,
    raw_tags: Any,
    now: datetime,
) -> None:
    for name in _parse_tags(raw_tags):
        tag_id = _insert_tag(connection, cache, owner_id=owner_id, name=name, now=now)
        connection.execute(record_entry_tags.insert().values(record_id=record_id, tag_id=tag_id))


def _backfill_book_records(
    connection: sa.Connection,
    owner_id: int | None,
    tag_cache: dict[tuple[int | None, str], int],
) -> None:
    for row in connection.execute(sa.select(book_records)).mappings():
        occurred_at = _record_time(
            row["last_read_at"],
            row["finished_at"],
            row["updated_at"],
            row["created_at"],
        )
        created_at = _record_time(row["created_at"], occurred_at)
        updated_at = _record_time(row["updated_at"], created_at)
        source = str(row["source"] or "weread")
        source_key = str(row["source_id"] or row["id"])
        entry_id = _insert_entry(
            connection,
            owner_id=owner_id,
            kind="reading",
            source=source,
            source_key=source_key,
            title=str(row["title"] or "未命名书籍"),
            summary=str(row["note_summary"] or ""),
            visibility=_normalize_visibility(row["visibility"]),
            occurred_at=occurred_at,
            created_at=created_at,
            updated_at=updated_at,
        )
        connection.execute(
            book_records.update()
            .where(book_records.c.id == row["id"])
            .values(record_entry_id=entry_id)
        )
        _link_tags(
            connection,
            tag_cache,
            record_id=entry_id,
            owner_id=owner_id,
            raw_tags=row["tags_json"],
            now=updated_at,
        )


def _backfill_movie_records(
    connection: sa.Connection,
    owner_id: int | None,
    tag_cache: dict[tuple[int | None, str], int],
) -> None:
    for row in connection.execute(sa.select(movie_records)).mappings():
        occurred_at = _record_time(row["watched_at"], row["updated_at"], row["created_at"])
        created_at = _record_time(row["created_at"], occurred_at)
        updated_at = _record_time(row["updated_at"], created_at)
        source = str(row["source"] or "manual")
        source_key = str(row["source_id"] or row["id"])
        entry_id = _insert_entry(
            connection,
            owner_id=owner_id,
            kind="movie",
            source=source,
            source_key=source_key,
            title=str(row["title"] or "未命名电影"),
            summary=str(row["note"] or ""),
            visibility=_normalize_visibility(row["visibility"]),
            occurred_at=occurred_at,
            created_at=created_at,
            updated_at=updated_at,
        )
        connection.execute(
            movie_records.update()
            .where(movie_records.c.id == row["id"])
            .values(record_entry_id=entry_id)
        )
        _link_tags(
            connection,
            tag_cache,
            record_id=entry_id,
            owner_id=owner_id,
            raw_tags=row["tags_json"],
            now=updated_at,
        )


def _add_record_entry_link(table_name: str, constraint_name: str) -> None:
    # batch_alter_table 让 SQLite 离线/测试环境也能创建外键，生产 PostgreSQL/MySQL 仍使用原生 ALTER。
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column("record_entry_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            constraint_name,
            "record_entries",
            ["record_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )


def upgrade() -> None:
    op.create_table(
        "record_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("source_key", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_record_entries_owner_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "source", "source_key", name="uq_record_entries_kind_source_key"),
    )
    op.create_index("ix_record_entries_owner_occurred_at", "record_entries", ["owner_id", "occurred_at"])
    op.create_index("ix_record_entries_kind_occurred_at", "record_entries", ["kind", "occurred_at"])
    op.create_index("ix_record_entries_visibility", "record_entries", ["visibility"])

    op.create_table(
        "record_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False, server_default="#8ca093"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_record_tags_owner_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_record_tags_owner_name"),
    )
    op.create_index("ix_record_tags_owner_id", "record_tags", ["owner_id"])
    op.create_index("ix_record_tags_slug", "record_tags", ["slug"])

    op.create_table(
        "record_entry_tags",
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["record_entries.id"],
            name="fk_record_entry_tags_record_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["record_tags.id"],
            name="fk_record_entry_tags_tag_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id", "tag_id"),
    )

    op.create_table(
        "note_records",
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="markdown"),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["record_entries.id"],
            name="fk_note_records_record_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id"),
    )

    op.create_table(
        "focus_sessions",
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=255), nullable=False),
        sa.Column("project", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["record_entries.id"],
            name="fk_focus_sessions_record_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_focus_sessions_started_at", "focus_sessions", ["started_at"])

    _add_record_entry_link("book_records", "fk_book_records_record_entry_id")
    _add_record_entry_link("movie_records", "fk_movie_records_record_entry_id")
    op.create_index("uq_book_records_record_entry_id", "book_records", ["record_entry_id"], unique=True)
    op.create_index("uq_movie_records_record_entry_id", "movie_records", ["record_entry_id"], unique=True)

    connection = op.get_bind()
    owner_id = _first_owner_id(connection)
    tag_cache: dict[tuple[int | None, str], int] = {}
    _backfill_book_records(connection, owner_id, tag_cache)
    _backfill_movie_records(connection, owner_id, tag_cache)


def downgrade() -> None:
    op.drop_index("uq_movie_records_record_entry_id", table_name="movie_records")
    with op.batch_alter_table("movie_records") as batch:
        batch.drop_constraint("fk_movie_records_record_entry_id", type_="foreignkey")
        batch.drop_column("record_entry_id")

    op.drop_index("uq_book_records_record_entry_id", table_name="book_records")
    with op.batch_alter_table("book_records") as batch:
        batch.drop_constraint("fk_book_records_record_entry_id", type_="foreignkey")
        batch.drop_column("record_entry_id")

    op.drop_index("ix_focus_sessions_started_at", table_name="focus_sessions")
    op.drop_table("focus_sessions")
    op.drop_table("note_records")
    op.drop_table("record_entry_tags")

    op.drop_index("ix_record_tags_slug", table_name="record_tags")
    op.drop_index("ix_record_tags_owner_id", table_name="record_tags")
    op.drop_table("record_tags")

    op.drop_index("ix_record_entries_visibility", table_name="record_entries")
    op.drop_index("ix_record_entries_kind_occurred_at", table_name="record_entries")
    op.drop_index("ix_record_entries_owner_occurred_at", table_name="record_entries")
    op.drop_table("record_entries")
