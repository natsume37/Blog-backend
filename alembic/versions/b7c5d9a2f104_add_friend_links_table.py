"""add_friend_links_table

Revision ID: b7c5d9a2f104
Revises: f3b4c7d8e921
Create Date: 2026-03-09 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c5d9a2f104"
down_revision: Union[str, Sequence[str], None] = "f3b4c7d8e921"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "friend_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("logo", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("description", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("group_name", sa.String(length=50), nullable=True, server_default="推荐站点"),
        sa.Column("contact", sa.String(length=120), nullable=True, server_default=""),
        sa.Column("reciprocal_url", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("site_color", sa.String(length=20), nullable=True, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.UniqueConstraint("url", name="uq_friend_links_url"),
    )
    op.create_index("ix_friend_links_id", "friend_links", ["id"], unique=False)
    op.create_index("ix_friend_links_status", "friend_links", ["status"], unique=False)
    op.create_index("ix_friend_links_sort_order", "friend_links", ["sort_order"], unique=False)
    op.create_index("ix_friend_links_group_name", "friend_links", ["group_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_friend_links_group_name", table_name="friend_links")
    op.drop_index("ix_friend_links_sort_order", table_name="friend_links")
    op.drop_index("ix_friend_links_status", table_name="friend_links")
    op.drop_index("ix_friend_links_id", table_name="friend_links")
    op.drop_table("friend_links")
