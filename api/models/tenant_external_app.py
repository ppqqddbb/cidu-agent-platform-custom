"""Tenant-scoped third-party application and API registry models.

The registry stores per-tenant third-party app instances and the callable
API definitions exposed by each app. Dify only stores metadata needed for
tool routing and manual confirmation; downstream data permissions remain
enforced by third-party systems.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from libs.datetime_utils import naive_utc_now

from .base import TypeBase
from .types import EnumText, StringUUID


class TenantExternalAppAuthMode(enum.StrEnum):
    NONE = "none"
    STATIC_BEARER = "static_bearer"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    OAUTH2_AUTHORIZATION_CODE = "oauth2_authorization_code"
    CUSTOM = "custom"


class TenantExternalAppApiSource(enum.StrEnum):
    MANUAL = "manual"
    OPENAPI_IMPORT = "openapi_import"


class TenantExternalApp(TypeBase):
    """A third-party app instance registered under one tenant."""

    __tablename__ = "tenant_external_apps"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="tenant_external_app_pkey"),
        sa.UniqueConstraint("tenant_id", "name", name="tenant_external_app_tenant_name_key"),
        sa.Index("tenant_external_app_tenant_created_idx", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    app_purpose: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    auth_mode: Mapped[TenantExternalAppAuthMode] = mapped_column(
        EnumText(TenantExternalAppAuthMode, length=64),
        server_default=sa.text("'none'"),
        default=TenantExternalAppAuthMode.NONE,
    )
    auth_config: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False, default_factory=dict)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.text("true"),
        default=True,
    )
    created_by_account_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    updated_by_account_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )


class TenantExternalAppApi(TypeBase):
    """Callable API metadata for a tenant external app."""

    __tablename__ = "tenant_external_app_apis"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="tenant_external_app_api_pkey"),
        sa.UniqueConstraint(
            "tenant_id",
            "app_id",
            "http_method",
            "path",
            name="tenant_external_app_api_identity_key",
        ),
        sa.Index("tenant_external_app_api_tenant_app_idx", "tenant_id", "app_id"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID)
    app_id: Mapped[str] = mapped_column(StringUUID)
    name: Mapped[str] = mapped_column(String(255))
    http_method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(1024))
    summary: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    api_purpose: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    source: Mapped[TenantExternalAppApiSource] = mapped_column(
        EnumText(TenantExternalAppApiSource, length=32),
        server_default=sa.text("'manual'"),
        default=TenantExternalAppApiSource.MANUAL,
    )
    source_version: Mapped[int] = mapped_column(sa.BigInteger, server_default=sa.text("1"), default=1)
    required_permissions: Mapped[list[str]] = mapped_column(sa.JSON, nullable=False, default_factory=list)
    request_schema: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False, default_factory=dict)
    response_schema: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False, default_factory=dict)
    is_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.text("true"),
        default=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.text("true"),
        default=True,
    )
    created_by_account_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    updated_by_account_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default_factory=naive_utc_now)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )
