"""add tenant external app tables

Revision ID: c4a1a2d3e4f5
Revises: 8f3e1c2a4b5d
Create Date: 2026-04-13 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

import models.types
from models.tenant_external_app import TenantExternalAppApiSource, TenantExternalAppAuthMode

# revision identifiers, used by Alembic.
revision = "c4a1a2d3e4f5"
down_revision = "8f3e1c2a4b5d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_external_apps",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("app_purpose", sa.Text(), nullable=True),
        sa.Column(
            "auth_mode",
            models.types.EnumText(TenantExternalAppAuthMode, length=64),
            server_default=sa.text("'none'"),
            nullable=False,
        ),
        sa.Column("auth_config", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_account_id", models.types.StringUUID(), nullable=True),
        sa.Column("updated_by_account_id", models.types.StringUUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="tenant_external_app_pkey"),
        sa.UniqueConstraint("tenant_id", "name", name="tenant_external_app_tenant_name_key"),
    )
    op.create_index(
        "tenant_external_app_tenant_created_idx",
        "tenant_external_apps",
        ["tenant_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "tenant_external_app_apis",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("app_id", models.types.StringUUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("http_method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("api_purpose", sa.Text(), nullable=True),
        sa.Column(
            "source",
            models.types.EnumText(TenantExternalAppApiSource, length=32),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column("source_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("required_permissions", sa.JSON(), nullable=False),
        sa.Column("request_schema", sa.JSON(), nullable=False),
        sa.Column("response_schema", sa.JSON(), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_account_id", models.types.StringUUID(), nullable=True),
        sa.Column("updated_by_account_id", models.types.StringUUID(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="tenant_external_app_api_pkey"),
        sa.UniqueConstraint(
            "tenant_id",
            "app_id",
            "http_method",
            "path",
            name="tenant_external_app_api_identity_key",
        ),
    )
    op.create_index(
        "tenant_external_app_api_tenant_app_idx",
        "tenant_external_app_apis",
        ["tenant_id", "app_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("tenant_external_app_api_tenant_app_idx", table_name="tenant_external_app_apis")
    op.drop_table("tenant_external_app_apis")

    op.drop_index("tenant_external_app_tenant_created_idx", table_name="tenant_external_apps")
    op.drop_table("tenant_external_apps")
