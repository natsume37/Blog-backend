"""default records to admin visibility

Revision ID: b6f1e2d3c4a5
Revises: a5d6e7f8c901
Create Date: 2026-05-17 23:25:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6f1e2d3c4a5"
down_revision: Union[str, None] = "a5d6e7f8c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "book_records",
        "visibility",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="private",
    )
    op.alter_column(
        "movie_records",
        "visibility",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="private",
    )
    op.execute("UPDATE book_records SET visibility = 'private' WHERE source = 'weread' AND visibility = 'public'")
    op.execute("UPDATE movie_records SET visibility = 'private' WHERE visibility = 'public'")


def downgrade() -> None:
    op.alter_column(
        "book_records",
        "visibility",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="public",
    )
    op.alter_column(
        "movie_records",
        "visibility",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="public",
    )
