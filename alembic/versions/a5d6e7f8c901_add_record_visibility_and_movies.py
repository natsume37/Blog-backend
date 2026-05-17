"""add record visibility and movies

Revision ID: a5d6e7f8c901
Revises: e7b8c9d0a1f2
Create Date: 2026-05-17 22:45:00.000000
"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5d6e7f8c901"
down_revision: Union[str, None] = "e7b8c9d0a1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


movie_records = sa.table(
    "movie_records",
    sa.column("source", sa.String),
    sa.column("source_id", sa.String),
    sa.column("title", sa.String),
    sa.column("director", sa.String),
    sa.column("cover", sa.String),
    sa.column("format", sa.String),
    sa.column("status", sa.String),
    sa.column("progress", sa.Integer),
    sa.column("rating", sa.Integer),
    sa.column("duration_minutes", sa.Integer),
    sa.column("note", sa.Text),
    sa.column("tags_json", sa.Text),
    sa.column("color", sa.String),
    sa.column("accent", sa.String),
    sa.column("visibility", sa.String),
    sa.column("is_top", sa.Boolean),
    sa.column("watched_at", sa.DateTime),
)


def upgrade() -> None:
    op.add_column(
        "book_records",
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="public"),
    )
    op.create_index(op.f("ix_book_records_visibility"), "book_records", ["visibility"], unique=False)
    op.execute("UPDATE book_records SET visibility = 'private' WHERE is_private = 1")

    op.create_table(
        "movie_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("director", sa.String(length=255), nullable=True),
        sa.Column("cover", sa.String(length=500), nullable=True),
        sa.Column("format", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("accent", sa.String(length=20), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="public"),
        sa.Column("is_top", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("watched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(op.f("ix_movie_records_id"), "movie_records", ["id"], unique=False)
    op.create_index(op.f("ix_movie_records_source"), "movie_records", ["source"], unique=False)
    op.create_index(op.f("ix_movie_records_source_id"), "movie_records", ["source_id"], unique=False)
    op.create_index(op.f("ix_movie_records_status"), "movie_records", ["status"], unique=False)
    op.create_index(op.f("ix_movie_records_visibility"), "movie_records", ["visibility"], unique=False)

    op.bulk_insert(
        movie_records,
        [
            {
                "source": "manual",
                "source_id": "perfect-days",
                "title": "Perfect Days",
                "director": "Wim Wenders",
                "cover": "",
                "format": "影院",
                "status": "已看完",
                "progress": 100,
                "rating": 45,
                "duration_minutes": 124,
                "note": "日常动作的重复感很克制，适合写一篇关于生活秩序的短评。",
                "tags_json": '["剧情", "日本", "摄影"]',
                "color": "#2f5d7c",
                "accent": "#d6a35d",
                "visibility": "public",
                "is_top": False,
                "watched_at": datetime(2026, 5, 15),
            },
            {
                "source": "manual",
                "source_id": "dune-part-two",
                "title": "沙丘 2",
                "director": "Denis Villeneuve",
                "cover": "",
                "format": "IMAX",
                "status": "想看",
                "progress": 0,
                "rating": 0,
                "duration_minutes": 166,
                "note": "先补原著设定和第一部视觉笔记，再决定是否写长评。",
                "tags_json": '["科幻", "视觉", "待购票"]',
                "color": "#b66a2f",
                "accent": "#203441",
                "visibility": "public",
                "is_top": False,
                "watched_at": datetime(2026, 5, 18),
            },
            {
                "source": "manual",
                "source_id": "anatomy-of-a-fall",
                "title": "坠落的审判",
                "director": "Justine Triet",
                "cover": "",
                "format": "流媒体",
                "status": "已看完",
                "progress": 100,
                "rating": 50,
                "duration_minutes": 151,
                "note": "法庭叙事与亲密关系的边界很值得拆镜头。",
                "tags_json": '["悬疑", "法庭", "长评"]',
                "color": "#7b3449",
                "accent": "#152029",
                "visibility": "public",
                "is_top": False,
                "watched_at": datetime(2026, 5, 9),
            },
            {
                "source": "manual",
                "source_id": "in-the-mood-for-love",
                "title": "花样年华",
                "director": "王家卫",
                "cover": "",
                "format": "蓝光",
                "status": "重看中",
                "progress": 56,
                "rating": 50,
                "duration_minutes": 98,
                "note": "把门框、走廊、慢动作剪成一组视觉索引。",
                "tags_json": '["爱情", "摄影", "重看"]',
                "color": "#8f2d2d",
                "accent": "#1e1613",
                "visibility": "public",
                "is_top": False,
                "watched_at": datetime(2026, 4, 30),
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_movie_records_visibility"), table_name="movie_records")
    op.drop_index(op.f("ix_movie_records_status"), table_name="movie_records")
    op.drop_index(op.f("ix_movie_records_source_id"), table_name="movie_records")
    op.drop_index(op.f("ix_movie_records_source"), table_name="movie_records")
    op.drop_index(op.f("ix_movie_records_id"), table_name="movie_records")
    op.drop_table("movie_records")

    op.drop_index(op.f("ix_book_records_visibility"), table_name="book_records")
    op.drop_column("book_records", "visibility")
