"""add github oauth fields

Revision ID: c7d8e9f0a1b2
Revises: b6f1e2d3c4a5
Create Date: 2026-05-18 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b6f1e2d3c4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_id", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("github_login", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_users_github_id"), "users", ["github_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_github_id"), table_name="users")
    op.drop_column("users", "github_login")
    op.drop_column("users", "github_id")
