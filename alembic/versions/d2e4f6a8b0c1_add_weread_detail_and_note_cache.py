"""add weread detail and note cache

Revision ID: d2e4f6a8b0c1
Revises: c7d8e9f0a1b2
Create Date: 2026-05-18 02:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e4f6a8b0c1"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("book_records", sa.Column("publisher", sa.String(length=255), nullable=True))
    op.add_column("book_records", sa.Column("publish_time", sa.String(length=80), nullable=True))
    op.add_column("book_records", sa.Column("isbn", sa.String(length=80), nullable=True))
    op.add_column("book_records", sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("book_records", sa.Column("weread_rating", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("book_records", sa.Column("weread_rating_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("book_records", sa.Column("chapter_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("book_records", sa.Column("detail_synced_at", sa.DateTime(), nullable=True))

    op.create_table(
        "book_search_caches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("translator", sa.String(length=255), nullable=True),
        sa.Column("cover", sa.String(length=500), nullable=True),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("publish_time", sa.String(length=80), nullable=True),
        sa.Column("isbn", sa.String(length=80), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reading_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pay_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("soldout", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("search_keyword", sa.String(length=255), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(op.f("ix_book_search_caches_id"), "book_search_caches", ["id"], unique=False)
    op.create_index(op.f("ix_book_search_caches_search_keyword"), "book_search_caches", ["search_keyword"], unique=False)
    op.create_index(op.f("ix_book_search_caches_source"), "book_search_caches", ["source"], unique=False)
    op.create_index(op.f("ix_book_search_caches_source_id"), "book_search_caches", ["source_id"], unique=False)

    op.create_table(
        "book_note_caches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_record_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_book_id", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("note_type", sa.String(length=30), nullable=False),
        sa.Column("chapter_uid", sa.String(length=80), nullable=True),
        sa.Column("chapter_title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("location_range", sa.String(length=80), nullable=True),
        sa.Column("color_style", sa.String(length=30), nullable=True),
        sa.Column("deep_link", sa.String(length=500), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["book_record_id"], ["book_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_book_id", "source_id", "note_type", name="uq_book_note_cache_source"),
    )
    op.create_index(op.f("ix_book_note_caches_book_record_id"), "book_note_caches", ["book_record_id"], unique=False)
    op.create_index(op.f("ix_book_note_caches_chapter_uid"), "book_note_caches", ["chapter_uid"], unique=False)
    op.create_index(op.f("ix_book_note_caches_id"), "book_note_caches", ["id"], unique=False)
    op.create_index(op.f("ix_book_note_caches_note_type"), "book_note_caches", ["note_type"], unique=False)
    op.create_index(op.f("ix_book_note_caches_source"), "book_note_caches", ["source"], unique=False)
    op.create_index(op.f("ix_book_note_caches_source_book_id"), "book_note_caches", ["source_book_id"], unique=False)
    op.create_index(op.f("ix_book_note_caches_source_id"), "book_note_caches", ["source_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_book_note_caches_source_id"), table_name="book_note_caches")
    op.drop_index(op.f("ix_book_note_caches_source_book_id"), table_name="book_note_caches")
    op.drop_index(op.f("ix_book_note_caches_source"), table_name="book_note_caches")
    op.drop_index(op.f("ix_book_note_caches_note_type"), table_name="book_note_caches")
    op.drop_index(op.f("ix_book_note_caches_id"), table_name="book_note_caches")
    op.drop_index(op.f("ix_book_note_caches_chapter_uid"), table_name="book_note_caches")
    op.drop_index(op.f("ix_book_note_caches_book_record_id"), table_name="book_note_caches")
    op.drop_table("book_note_caches")

    op.drop_index(op.f("ix_book_search_caches_source_id"), table_name="book_search_caches")
    op.drop_index(op.f("ix_book_search_caches_source"), table_name="book_search_caches")
    op.drop_index(op.f("ix_book_search_caches_search_keyword"), table_name="book_search_caches")
    op.drop_index(op.f("ix_book_search_caches_id"), table_name="book_search_caches")
    op.drop_table("book_search_caches")

    op.drop_column("book_records", "detail_synced_at")
    op.drop_column("book_records", "chapter_count")
    op.drop_column("book_records", "weread_rating_count")
    op.drop_column("book_records", "weread_rating")
    op.drop_column("book_records", "word_count")
    op.drop_column("book_records", "isbn")
    op.drop_column("book_records", "publish_time")
    op.drop_column("book_records", "publisher")
