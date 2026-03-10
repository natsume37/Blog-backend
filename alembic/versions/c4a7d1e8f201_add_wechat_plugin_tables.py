"""add wechat plugin tables

Revision ID: c4a7d1e8f201
Revises: ab91b6f89a31
Create Date: 2026-03-11 10:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4a7d1e8f201"
down_revision: Union[str, Sequence[str], None] = "ab91b6f89a31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wechat_broadcast_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("draft_media_id", sa.String(length=255), nullable=True),
        sa.Column("broadcast_media_id", sa.String(length=255), nullable=True),
        sa.Column("publish_id", sa.String(length=255), nullable=True),
        sa.Column("msg_id", sa.String(length=255), nullable=True),
        sa.Column("preview_target", sa.String(length=255), nullable=True),
        sa.Column("audience_type", sa.String(length=32), nullable=False),
        sa.Column("audience_value", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("status_text", sa.String(length=255), nullable=True),
        sa.Column("request_payload", sa.Text(), nullable=True),
        sa.Column("response_payload", sa.Text(), nullable=True),
        sa.Column("result_payload", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wechat_broadcast_tasks_id", "wechat_broadcast_tasks", ["id"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_task_type", "wechat_broadcast_tasks", ["task_type"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_source_type", "wechat_broadcast_tasks", ["source_type"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_article_id", "wechat_broadcast_tasks", ["article_id"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_draft_media_id", "wechat_broadcast_tasks", ["draft_media_id"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_broadcast_media_id", "wechat_broadcast_tasks", ["broadcast_media_id"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_publish_id", "wechat_broadcast_tasks", ["publish_id"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_msg_id", "wechat_broadcast_tasks", ["msg_id"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_status", "wechat_broadcast_tasks", ["status"], unique=False)
    op.create_index("ix_wechat_broadcast_tasks_created_by", "wechat_broadcast_tasks", ["created_by"], unique=False)

    op.create_table(
        "wechat_qrcode_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("action_name", sa.String(length=32), nullable=False),
        sa.Column("scene_type", sa.String(length=16), nullable=False),
        sa.Column("scene_value", sa.String(length=255), nullable=False),
        sa.Column("ticket", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("expire_seconds", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("request_payload", sa.Text(), nullable=True),
        sa.Column("response_payload", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket"),
    )
    op.create_index("ix_wechat_qrcode_records_id", "wechat_qrcode_records", ["id"], unique=False)
    op.create_index("ix_wechat_qrcode_records_action_name", "wechat_qrcode_records", ["action_name"], unique=False)
    op.create_index("ix_wechat_qrcode_records_scene_value", "wechat_qrcode_records", ["scene_value"], unique=False)
    op.create_index("ix_wechat_qrcode_records_expires_at", "wechat_qrcode_records", ["expires_at"], unique=False)
    op.create_index("ix_wechat_qrcode_records_created_by", "wechat_qrcode_records", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wechat_qrcode_records_created_by", table_name="wechat_qrcode_records")
    op.drop_index("ix_wechat_qrcode_records_expires_at", table_name="wechat_qrcode_records")
    op.drop_index("ix_wechat_qrcode_records_scene_value", table_name="wechat_qrcode_records")
    op.drop_index("ix_wechat_qrcode_records_action_name", table_name="wechat_qrcode_records")
    op.drop_index("ix_wechat_qrcode_records_id", table_name="wechat_qrcode_records")
    op.drop_table("wechat_qrcode_records")

    op.drop_index("ix_wechat_broadcast_tasks_created_by", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_status", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_msg_id", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_publish_id", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_broadcast_media_id", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_draft_media_id", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_article_id", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_source_type", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_task_type", table_name="wechat_broadcast_tasks")
    op.drop_index("ix_wechat_broadcast_tasks_id", table_name="wechat_broadcast_tasks")
    op.drop_table("wechat_broadcast_tasks")
