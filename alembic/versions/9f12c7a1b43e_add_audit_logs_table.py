"""add_audit_logs_table

Revision ID: 9f12c7a1b43e
Revises: 63c9d7e5f1a2
Create Date: 2026-03-06 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f12c7a1b43e"
down_revision: Union[str, Sequence[str], None] = "63c9d7e5f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("target_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("target_id", sa.String(length=64), nullable=True, server_default=""),
        sa.Column("description", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("request_path", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("request_method", sa.String(length=10), nullable=True, server_default=""),
        sa.Column("ip", sa.String(length=50), nullable=True, server_default=""),
        sa.Column("user_agent", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("extra", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"], unique=False)
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)
    op.create_index("ix_audit_logs_username", "audit_logs", ["username"], unique=False)
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_target_type", "audit_logs", ["target_type"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_username", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_id", table_name="audit_logs")
    op.drop_table("audit_logs")
