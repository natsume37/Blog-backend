"""add plugin tables

Revision ID: ab91b6f89a31
Revises: b7c5d9a2f104
Create Date: 2026-03-10 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ab91b6f89a31"
down_revision: Union[str, Sequence[str], None] = "b7c5d9a2f104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_installs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plugin_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("is_installed", sa.Boolean(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=True),
        sa.Column("installed_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id"),
    )
    op.create_index(op.f("ix_plugin_installs_id"), "plugin_installs", ["id"], unique=False)
    op.create_index(op.f("ix_plugin_installs_plugin_id"), "plugin_installs", ["plugin_id"], unique=False)

    op.create_table(
        "plugin_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plugin_id", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id", "key", name="uq_plugin_settings_plugin_key"),
    )
    op.create_index(op.f("ix_plugin_settings_id"), "plugin_settings", ["id"], unique=False)
    op.create_index(op.f("ix_plugin_settings_plugin_id"), "plugin_settings", ["plugin_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_plugin_settings_plugin_id"), table_name="plugin_settings")
    op.drop_index(op.f("ix_plugin_settings_id"), table_name="plugin_settings")
    op.drop_table("plugin_settings")

    op.drop_index(op.f("ix_plugin_installs_plugin_id"), table_name="plugin_installs")
    op.drop_index(op.f("ix_plugin_installs_id"), table_name="plugin_installs")
    op.drop_table("plugin_installs")
