"""add_tool_items_table

Revision ID: f1c2d3e4a5b6
Revises: c4a7d1e8f201
Create Date: 2026-03-13 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1c2d3e4a5b6"
down_revision: Union[str, Sequence[str], None] = "c4a7d1e8f201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("logo", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("description", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("category", sa.String(length=50), nullable=True, server_default="推荐工具"),
        sa.Column("tool_type", sa.String(length=30), nullable=True, server_default="website"),
        sa.Column("badge", sa.String(length=40), nullable=True, server_default=""),
        sa.Column("tags", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("site_color", sa.String(length=20), nullable=True, server_default=""),
        sa.Column("subscription_url", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("open_mode", sa.String(length=20), nullable=False, server_default="new_tab"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.UniqueConstraint("url", name="uq_tool_items_url"),
    )
    op.create_index("ix_tool_items_id", "tool_items", ["id"], unique=False)
    op.create_index("ix_tool_items_status", "tool_items", ["status"], unique=False)
    op.create_index("ix_tool_items_sort_order", "tool_items", ["sort_order"], unique=False)
    op.create_index("ix_tool_items_category", "tool_items", ["category"], unique=False)
    op.create_index("ix_tool_items_tool_type", "tool_items", ["tool_type"], unique=False)

    tool_items_table = sa.table(
        "tool_items",
        sa.column("name", sa.String(length=100)),
        sa.column("url", sa.String(length=500)),
        sa.column("logo", sa.String(length=500)),
        sa.column("description", sa.String(length=255)),
        sa.column("category", sa.String(length=50)),
        sa.column("tool_type", sa.String(length=30)),
        sa.column("badge", sa.String(length=40)),
        sa.column("tags", sa.String(length=255)),
        sa.column("site_color", sa.String(length=20)),
        sa.column("subscription_url", sa.String(length=500)),
        sa.column("open_mode", sa.String(length=20)),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_featured", sa.Boolean()),
        sa.column("status", sa.String(length=20)),
    )
    op.bulk_insert(
        tool_items_table,
        [
            {
                "name": "NewsNow",
                "url": "https://newsnow.busiyi.world/",
                "logo": "",
                "description": "聚合多源实时新闻的快读站点，适合放在工具墙里作为资讯入口。",
                "category": "资讯雷达",
                "tool_type": "news",
                "badge": "实时",
                "tags": "新闻,实时,聚合",
                "site_color": "#ef4444",
                "subscription_url": "",
                "open_mode": "new_tab",
                "sort_order": 1,
                "is_featured": True,
                "status": "published",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_items_tool_type", table_name="tool_items")
    op.drop_index("ix_tool_items_category", table_name="tool_items")
    op.drop_index("ix_tool_items_sort_order", table_name="tool_items")
    op.drop_index("ix_tool_items_status", table_name="tool_items")
    op.drop_index("ix_tool_items_id", table_name="tool_items")
    op.drop_table("tool_items")
