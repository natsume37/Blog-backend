"""add article hidden field

Revision ID: 63c9d7e5f1a2
Revises: d4bff395db7d
Create Date: 2026-01-07 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63c9d7e5f1a2'
down_revision: Union[str, Sequence[str], None] = 'd4bff395db7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('is_hidden', sa.Boolean(), nullable=True, default=False, comment='是否隐藏(不显示在列表，但可通过链接访问)'))


def downgrade() -> None:
    op.drop_column('articles', 'is_hidden')
