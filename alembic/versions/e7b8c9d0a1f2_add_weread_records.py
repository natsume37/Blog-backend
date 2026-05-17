"""add weread records

Revision ID: e7b8c9d0a1f2
Revises: f1c2d3e4a5b6
Create Date: 2026-05-17 20:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b8c9d0a1f2"
down_revision: Union[str, None] = "f1c2d3e4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "book_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("cover", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("read_seconds", sa.Integer(), nullable=False),
        sa.Column("note_count", sa.Integer(), nullable=False),
        sa.Column("highlight_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("bookmark_count", sa.Integer(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("note_summary", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("accent", sa.String(length=20), nullable=True),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("is_top", sa.Boolean(), nullable=False),
        sa.Column("is_in_shelf", sa.Boolean(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(op.f("ix_book_records_id"), "book_records", ["id"], unique=False)
    op.create_index(op.f("ix_book_records_is_in_shelf"), "book_records", ["is_in_shelf"], unique=False)
    op.create_index(op.f("ix_book_records_source"), "book_records", ["source"], unique=False)
    op.create_index(op.f("ix_book_records_source_id"), "book_records", ["source_id"], unique=False)
    op.create_index(op.f("ix_book_records_status"), "book_records", ["status"], unique=False)

    op.create_table(
        "weread_sync_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("books_synced", sa.Integer(), nullable=False),
        sa.Column("notes_synced", sa.Integer(), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_weread_sync_state_id"), "weread_sync_state", ["id"], unique=False)

    op.create_table(
        "book_note_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_record_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("note_type", sa.String(length=30), nullable=False),
        sa.Column("chapter_title", sa.String(length=255), nullable=True),
        sa.Column("content_summary", sa.Text(), nullable=True),
        sa.Column("deep_link", sa.String(length=500), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["book_record_id"], ["book_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_book_note_summaries_book_record_id"), "book_note_summaries", ["book_record_id"], unique=False)
    op.create_index(op.f("ix_book_note_summaries_id"), "book_note_summaries", ["id"], unique=False)
    op.create_index(op.f("ix_book_note_summaries_source_id"), "book_note_summaries", ["source_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_book_note_summaries_source_id"), table_name="book_note_summaries")
    op.drop_index(op.f("ix_book_note_summaries_id"), table_name="book_note_summaries")
    op.drop_index(op.f("ix_book_note_summaries_book_record_id"), table_name="book_note_summaries")
    op.drop_table("book_note_summaries")
    op.drop_index(op.f("ix_weread_sync_state_id"), table_name="weread_sync_state")
    op.drop_table("weread_sync_state")
    op.drop_index(op.f("ix_book_records_status"), table_name="book_records")
    op.drop_index(op.f("ix_book_records_source_id"), table_name="book_records")
    op.drop_index(op.f("ix_book_records_source"), table_name="book_records")
    op.drop_index(op.f("ix_book_records_is_in_shelf"), table_name="book_records")
    op.drop_index(op.f("ix_book_records_id"), table_name="book_records")
    op.drop_table("book_records")
