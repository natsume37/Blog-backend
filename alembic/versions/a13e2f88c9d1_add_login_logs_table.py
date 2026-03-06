"""add_login_logs_table

Revision ID: a13e2f88c9d1
Revises: 9f12c7a1b43e
Create Date: 2026-03-06 16:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a13e2f88c9d1"
down_revision: Union[str, Sequence[str], None] = "9f12c7a1b43e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=50), nullable=True, server_default=""),
        sa.Column("user_agent", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("reason", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.create_index("ix_login_logs_id", "login_logs", ["id"], unique=False)
    op.create_index("ix_login_logs_user_id", "login_logs", ["user_id"], unique=False)
    op.create_index("ix_login_logs_username", "login_logs", ["username"], unique=False)
    op.create_index("ix_login_logs_success", "login_logs", ["success"], unique=False)
    op.create_index("ix_login_logs_created_at", "login_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_login_logs_created_at", table_name="login_logs")
    op.drop_index("ix_login_logs_success", table_name="login_logs")
    op.drop_index("ix_login_logs_username", table_name="login_logs")
    op.drop_index("ix_login_logs_user_id", table_name="login_logs")
    op.drop_index("ix_login_logs_id", table_name="login_logs")
    op.drop_table("login_logs")
