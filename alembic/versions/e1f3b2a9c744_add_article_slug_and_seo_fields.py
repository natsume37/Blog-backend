"""add_article_slug_and_seo_fields

Revision ID: e1f3b2a9c744
Revises: c8b9a7e2d441
Create Date: 2026-03-06 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f3b2a9c744"
down_revision: Union[str, Sequence[str], None] = "c8b9a7e2d441"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("slug", sa.String(length=255), nullable=True, comment="自定义URL slug"))
    op.add_column("articles", sa.Column("seo_title", sa.String(length=255), nullable=True, server_default="", comment="SEO标题"))
    op.add_column("articles", sa.Column("seo_description", sa.String(length=500), nullable=True, server_default="", comment="SEO描述"))
    op.add_column("articles", sa.Column("seo_keywords", sa.String(length=500), nullable=True, server_default="", comment="SEO关键词，逗号分隔"))
    op.create_index("ix_articles_slug", "articles", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_articles_slug", table_name="articles")
    op.drop_column("articles", "seo_keywords")
    op.drop_column("articles", "seo_description")
    op.drop_column("articles", "seo_title")
    op.drop_column("articles", "slug")
