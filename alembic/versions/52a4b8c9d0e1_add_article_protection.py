"""Add article protection fields

Revision ID: 52a4b8c9d0e1
Revises: 27ecd5cfca7c
Create Date: 2026-01-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52a4b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = '27ecd5cfca7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('is_protected', sa.Boolean(), nullable=True, default=False, comment='是否受保护'))
    op.add_column('articles', sa.Column('protection_question', sa.String(length=255), nullable=True, comment='验证问题'))
    op.add_column('articles', sa.Column('protection_answer', sa.String(length=255), nullable=True, comment='验证答案'))


def downgrade() -> None:
    op.drop_column('articles', 'protection_answer')
    op.drop_column('articles', 'protection_question')
    op.drop_column('articles', 'is_protected')
