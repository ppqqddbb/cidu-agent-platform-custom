"""add knowledge graphs

Revision ID: 202605070001
Revises: 4f9c2d6a7b8e
Create Date: 2026-05-07 00:00:01.000000

"""

import sqlalchemy as sa
from alembic import op

import models.types

revision = "202605070001"
down_revision = "4f9c2d6a7b8e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_graphs",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("created_by", models.types.StringUUID(), nullable=False),
        sa.Column("updated_by", models.types.StringUUID(), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="knowledge_graphs_tenant_id_name_unique"),
    )
    op.create_index("knowledge_graphs_tenant_id_created_at_idx", "knowledge_graphs", ["tenant_id", "created_at"])
    op.create_index("knowledge_graphs_tenant_id_name_idx", "knowledge_graphs", ["tenant_id", "name"])


def downgrade():
    op.drop_index("knowledge_graphs_tenant_id_name_idx", table_name="knowledge_graphs")
    op.drop_index("knowledge_graphs_tenant_id_created_at_idx", table_name="knowledge_graphs")
    op.drop_table("knowledge_graphs")
