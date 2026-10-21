"""add external identity tables

Revision ID: 8f3e1c2a4b5d
Revises: 6b5f9f8b1a2c
Create Date: 2026-04-09 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

import models.types
from models.account import TenantAccountRole
from models.external_identity import ExternalManagementMode, ExternalSyncStatus

# revision identifiers, used by Alembic.
revision = "8f3e1c2a4b5d"
down_revision = "6b5f9f8b1a2c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_tenant_bindings",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("external_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "management_mode",
            models.types.EnumText(ExternalManagementMode, length=32),
            server_default=sa.text("'local_managed'"),
            nullable=False,
        ),
        sa.Column("allow_local_member_override", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="external_tenant_binding_pkey"),
        sa.UniqueConstraint("external_tenant_id", name="external_tenant_binding_external_tenant_id_key"),
        sa.UniqueConstraint("tenant_id", name="external_tenant_binding_tenant_id_key"),
    )

    op.create_table(
        "external_account_bindings",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("account_id", models.types.StringUUID(), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="external_account_binding_pkey"),
        sa.UniqueConstraint("external_user_id", name="external_account_binding_external_user_id_key"),
        sa.UniqueConstraint("account_id", name="external_account_binding_account_id_key"),
    )

    op.create_table(
        "external_membership_bindings",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("external_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("account_id", models.types.StringUUID(), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "display_role",
            models.types.EnumText(TenantAccountRole, length=16),
            server_default=sa.text("'normal'"),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="external_membership_binding_pkey"),
        sa.UniqueConstraint(
            "external_tenant_id",
            "external_user_id",
            name="external_membership_binding_external_member_key",
        ),
        sa.UniqueConstraint("tenant_id", "account_id", name="external_membership_binding_local_member_key"),
    )
    op.create_index(
        "external_membership_binding_tenant_account_idx",
        "external_membership_bindings",
        ["tenant_id", "account_id"],
        unique=False,
    )

    op.create_table(
        "external_permission_projections",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("external_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("account_id", models.types.StringUUID(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="external_permission_projection_pkey"),
        sa.UniqueConstraint("tenant_id", "account_id", name="external_permission_projection_local_member_key"),
        sa.UniqueConstraint(
            "external_tenant_id",
            "external_user_id",
            name="external_permission_projection_external_member_key",
        ),
    )
    op.create_index(
        "external_permission_projection_expiry_idx",
        "external_permission_projections",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "external_sync_inbox",
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("external_tenant_id", sa.String(length=255), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column("status", models.types.EnumText(ExternalSyncStatus, length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="external_sync_inbox_pkey"),
        sa.UniqueConstraint("event_id", name="external_sync_inbox_event_id_key"),
    )
    op.create_index("external_sync_inbox_event_type_idx", "external_sync_inbox", ["event_type"], unique=False)


def downgrade():
    op.drop_index("external_sync_inbox_event_type_idx", table_name="external_sync_inbox")
    op.drop_table("external_sync_inbox")

    op.drop_index("external_permission_projection_expiry_idx", table_name="external_permission_projections")
    op.drop_table("external_permission_projections")

    op.drop_index("external_membership_binding_tenant_account_idx", table_name="external_membership_bindings")
    op.drop_table("external_membership_bindings")

    op.drop_table("external_account_bindings")
    op.drop_table("external_tenant_bindings")
