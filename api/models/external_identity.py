"""External identity and authorization projection models.

These tables let Dify consume tenant, account, membership, and authorization
state from an external system without replacing the local account / workspace
data model. The local `Tenant`, `Account`, and `TenantAccountJoin` rows remain
the runtime source for existing features, while these bindings and projections
track the external source-of-truth mapping plus sync metadata.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .account import TenantAccountRole
from .base import TypeBase
from .types import EnumText, StringUUID
from libs.datetime_utils import naive_utc_now


class ExternalManagementMode(enum.StrEnum):
    LOCAL_MANAGED = "local_managed"
    EXTERNAL_MANAGED = "external_managed"


class ExternalSyncStatus(enum.StrEnum):
    APPLIED = "applied"
    DUPLICATE_EVENT = "duplicate_event"
    STALE_VERSION = "stale_version"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    FAILED = "failed"


class ExternalTenantBinding(TypeBase):
    """Map one external tenant identity to one local Dify tenant."""

    __tablename__ = "external_tenant_bindings"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="external_tenant_binding_pkey"),
        sa.UniqueConstraint("external_tenant_id", name="external_tenant_binding_external_tenant_id_key"),
        sa.UniqueConstraint("tenant_id", name="external_tenant_binding_tenant_id_key"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    external_tenant_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(StringUUID)
    source_version: Mapped[int] = mapped_column(sa.BigInteger)
    management_mode: Mapped[ExternalManagementMode] = mapped_column(
        EnumText(ExternalManagementMode, length=32),
        server_default=sa.text("'local_managed'"),
        default=ExternalManagementMode.LOCAL_MANAGED,
    )
    allow_local_member_override: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.text("false"),
        default=False,
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        default_factory=naive_utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )


class ExternalAccountBinding(TypeBase):
    """Map one external user identity to one local Dify account."""

    __tablename__ = "external_account_bindings"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="external_account_binding_pkey"),
        sa.UniqueConstraint("external_user_id", name="external_account_binding_external_user_id_key"),
        sa.UniqueConstraint("account_id", name="external_account_binding_account_id_key"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    external_user_id: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str] = mapped_column(StringUUID)
    source_version: Mapped[int] = mapped_column(sa.BigInteger)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        default_factory=naive_utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )


class ExternalMembershipBinding(TypeBase):
    """Track membership sync state, including tombstones for delete ordering."""

    __tablename__ = "external_membership_bindings"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="external_membership_binding_pkey"),
        sa.UniqueConstraint(
            "external_tenant_id",
            "external_user_id",
            name="external_membership_binding_external_member_key",
        ),
        sa.UniqueConstraint("tenant_id", "account_id", name="external_membership_binding_local_member_key"),
        sa.Index("external_membership_binding_tenant_account_idx", "tenant_id", "account_id"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    external_tenant_id: Mapped[str] = mapped_column(String(255))
    external_user_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(StringUUID)
    account_id: Mapped[str] = mapped_column(StringUUID)
    source_version: Mapped[int] = mapped_column(sa.BigInteger)
    display_role: Mapped[TenantAccountRole] = mapped_column(
        EnumText(TenantAccountRole, length=16),
        server_default=sa.text("'normal'"),
        default=TenantAccountRole.NORMAL,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.text("false"),
        default=False,
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        default_factory=naive_utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )


class ExternalPermissionProjection(TypeBase):
    """Store the current external capability snapshot for one tenant member."""

    __tablename__ = "external_permission_projections"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="external_permission_projection_pkey"),
        sa.UniqueConstraint("tenant_id", "account_id", name="external_permission_projection_local_member_key"),
        sa.UniqueConstraint(
            "external_tenant_id",
            "external_user_id",
            name="external_permission_projection_external_member_key",
        ),
        sa.Index("external_permission_projection_expiry_idx", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    # SQLAlchemy 这里会把声明式模型转换成 dataclass；带 default/default_factory 的字段
    # 必须放在必填字段后面，否则导入模型时就会触发 “non-default argument follows
    # default argument” 的建模错误。
    external_tenant_id: Mapped[str] = mapped_column(String(255))
    external_user_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(StringUUID)
    account_id: Mapped[str] = mapped_column(StringUUID)
    source_version: Mapped[int] = mapped_column(sa.BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    capabilities: Mapped[list[str]] = mapped_column(sa.JSON, nullable=False, default_factory=list)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        default_factory=naive_utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )


class ExternalSyncInbox(TypeBase):
    """Persist sync event processing outcomes for idempotency and auditability."""

    __tablename__ = "external_sync_inbox"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="external_sync_inbox_pkey"),
        sa.UniqueConstraint("event_id", name="external_sync_inbox_event_id_key"),
        sa.Index("external_sync_inbox_event_type_idx", "event_type"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(255))
    # 这里同样要先声明必填字段，再声明有默认值的可选字段；
    # 否则 SQLAlchemy 的 dataclass 转换会在 import 阶段失败。
    source_version: Mapped[int] = mapped_column(sa.BigInteger)
    status: Mapped[ExternalSyncStatus] = mapped_column(EnumText(ExternalSyncStatus, length=32))
    external_tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    payload: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False, default_factory=dict)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )
