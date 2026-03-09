"""add_article_versions_table

Revision ID: f3b4c7d8e921
Revises: e1f3b2a9c744
Create Date: 2026-03-06 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3b4c7d8e921"
down_revision: Union[str, Sequence[str], None] = "e1f3b2a9c744"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("slug", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cover", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("seo_title", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("seo_description", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("seo_keywords", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("category_id", sa.Integer(), nullable=True),
        # MySQL does not allow defaults on TEXT columns.
        sa.Column("tag_ids", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_top", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_recommend", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_hidden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="public"),
        sa.Column("is_protected", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("protection_question", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.create_index("ix_article_versions_id", "article_versions", ["id"], unique=False)
    op.create_index("ix_article_versions_article_id", "article_versions", ["article_id"], unique=False)
    op.create_index("ix_article_versions_created_at", "article_versions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_article_versions_created_at", table_name="article_versions")
    op.drop_index("ix_article_versions_article_id", table_name="article_versions")
    op.drop_index("ix_article_versions_id", table_name="article_versions")
    op.drop_table("article_versions")
