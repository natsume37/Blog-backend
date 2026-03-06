"""add_article_visibility

Revision ID: c8b9a7e2d441
Revises: a13e2f88c9d1
Create Date: 2026-03-06 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8b9a7e2d441"
down_revision: Union[str, Sequence[str], None] = "a13e2f88c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "visibility",
            sa.String(length=20),
            nullable=False,
            server_default="public",
            comment="可见性: public/login/private",
        ),
    )


def downgrade() -> None:
    op.drop_column("articles", "visibility")
