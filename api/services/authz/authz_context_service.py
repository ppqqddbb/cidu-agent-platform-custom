"""Request-scoped authorization context loading for workspace capability checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import cast

from flask import g, has_request_context
from sqlalchemy import select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from libs.login import current_account_with_tenant
from models import (
    ExternalAccountBinding,
    ExternalManagementMode,
    ExternalMembershipBinding,
    ExternalPermissionProjection,
    ExternalTenantBinding,
    TenantAccountRole,
)
from models.account import Tenant, TenantAccountJoin
from services.authz.authorization_service import AuthorizationService
from services.errors.integration import ExternalBindingNotFoundError
from services.external_identity_service import ExternalIdentityService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AuthorizationContext:
    account_id: str
    tenant_id: str
    role: TenantAccountRole | None
    management_mode: ExternalManagementMode
    allow_local_member_override: bool
    capabilities: list[str] = field(default_factory=list)
    capability_source: str = "legacy_role"
    membership_active: bool = True
    projection_source_version: int | None = None
    projection_expires_at: datetime | None = None
    stale_projection_used: bool = False
    refresh_attempted: bool = False


class AuthzContextService:
    """Build the current workspace authorization context for one account."""

    # 中文注释：这里对应 Phase 0 冻结的“短时旧缓存兜底”策略，
    # projection 刚过期且回源失败时，最多只允许继续使用 5 分钟旧快照。
    STALE_PROJECTION_GRACE_PERIOD = timedelta(minutes=5)

    @classmethod
    def get_current_context(cls) -> AuthorizationContext:
        if has_request_context() and hasattr(g, "_authz_context"):
            return cast(AuthorizationContext, g._authz_context)

        account, tenant_id = current_account_with_tenant()
        context = cls.get_context(account_id=account.id, tenant_id=tenant_id, role=account.current_role)

        if has_request_context():
            g._authz_context = context

        return context

    @classmethod
    def get_context(
        cls,
        *,
        account_id: str,
        tenant_id: str,
        role: TenantAccountRole | str | None,
    ) -> AuthorizationContext:
        normalized_role = AuthorizationService.normalize_role(role)
        tenant_binding = cls._get_tenant_binding(tenant_id)

        if tenant_binding is None or tenant_binding.management_mode == ExternalManagementMode.LOCAL_MANAGED:
            return cls._build_local_context(
                account_id=account_id,
                tenant_id=tenant_id,
                role=normalized_role,
                tenant_binding=tenant_binding,
            )

        return cls._build_external_context(
            account_id=account_id,
            tenant_id=tenant_id,
            role=normalized_role,
            tenant_binding=tenant_binding,
        )

    @staticmethod
    def _get_tenant_binding(tenant_id: str) -> ExternalTenantBinding | None:
        return db.session.scalar(
            select(ExternalTenantBinding).where(ExternalTenantBinding.tenant_id == tenant_id).limit(1)
        )

    @staticmethod
    def _get_account_binding(account_id: str) -> ExternalAccountBinding | None:
        return db.session.scalar(
            select(ExternalAccountBinding).where(ExternalAccountBinding.account_id == account_id).limit(1)
        )

    @staticmethod
    def _get_membership_binding(tenant_id: str, account_id: str) -> ExternalMembershipBinding | None:
        return db.session.scalar(
            select(ExternalMembershipBinding)
            .where(
                ExternalMembershipBinding.tenant_id == tenant_id,
                ExternalMembershipBinding.account_id == account_id,
            )
            .limit(1)
        )

    @staticmethod
    def _get_projection(tenant_id: str, account_id: str) -> ExternalPermissionProjection | None:
        return db.session.scalar(
            select(ExternalPermissionProjection)
            .where(
                ExternalPermissionProjection.tenant_id == tenant_id,
                ExternalPermissionProjection.account_id == account_id,
            )
            .limit(1)
        )

    @staticmethod
    def _is_super_admin_account(account_id: str) -> bool:
        default_tenant_id = db.session.scalar(select(Tenant.id).order_by(Tenant.created_at.asc(), Tenant.id.asc()).limit(1))
        if default_tenant_id is None:
            return False

        return (
            db.session.scalar(
                select(TenantAccountJoin.id)
                .where(
                    TenantAccountJoin.tenant_id == default_tenant_id,
                    TenantAccountJoin.account_id == account_id,
                    TenantAccountJoin.role.in_([TenantAccountRole.OWNER, TenantAccountRole.ADMIN]),
                )
                .limit(1)
            )
            is not None
        )

    @classmethod
    def _build_local_context(
        cls,
        *,
        account_id: str,
        tenant_id: str,
        role: TenantAccountRole | None,
        tenant_binding: ExternalTenantBinding | None,
    ) -> AuthorizationContext:
        return AuthorizationContext(
            account_id=account_id,
            tenant_id=tenant_id,
            role=role,
            management_mode=tenant_binding.management_mode if tenant_binding else ExternalManagementMode.LOCAL_MANAGED,
            allow_local_member_override=tenant_binding.allow_local_member_override if tenant_binding else False,
            capabilities=AuthorizationService.get_capabilities_for_role(role),
            capability_source="legacy_role",
            membership_active=True,
        )

    @classmethod
    def _build_external_context(
        cls,
        *,
        account_id: str,
        tenant_id: str,
        role: TenantAccountRole | None,
        tenant_binding: ExternalTenantBinding,
    ) -> AuthorizationContext:
        account_binding = cls._get_account_binding(account_id)
        membership_binding = cls._get_membership_binding(tenant_id, account_id)
        projection = cls._get_projection(tenant_id, account_id)
        now = naive_utc_now()
        membership_active = membership_binding is not None and not membership_binding.is_deleted

        if projection is not None and membership_active and projection.expires_at > now:
            return cls._build_projection_context(
                account_id=account_id,
                tenant_id=tenant_id,
                role=role,
                tenant_binding=tenant_binding,
                capabilities=projection.capabilities,
                source="projection",
                projection_source_version=projection.source_version,
                projection_expires_at=projection.expires_at,
            )

        resolved_context: AuthorizationContext | None = None
        refresh_attempted = account_binding is not None
        if account_binding is not None:
            resolved_context = cls._try_refresh_external_context(
                account_id=account_id,
                tenant_id=tenant_id,
                role=role,
                tenant_binding=tenant_binding,
                account_binding=account_binding,
                now=now,
            )
            if resolved_context is not None:
                resolved_context.refresh_attempted = True
                return resolved_context
        else:
            if cls._is_super_admin_account(account_id):
                logger.warning(
                    "external managed workspace missing account binding, fallback to super-admin role: "
                    "tenant_id=%s account_id=%s",
                    tenant_id,
                    account_id,
                )
                return AuthorizationContext(
                    account_id=account_id,
                    tenant_id=tenant_id,
                    role=role,
                    management_mode=tenant_binding.management_mode,
                    allow_local_member_override=tenant_binding.allow_local_member_override,
                    capabilities=AuthorizationService.get_capabilities_for_role(role),
                    capability_source="super_admin_legacy_fallback",
                    membership_active=True,
                    refresh_attempted=False,
                )
            logger.warning(
                "external managed workspace missing account binding: tenant_id=%s account_id=%s",
                tenant_id,
                account_id,
            )

        if (
            projection is not None
            and membership_active
            and projection.expires_at + cls.STALE_PROJECTION_GRACE_PERIOD > now
        ):
            logger.warning(
                "using stale local projection after refresh miss: tenant_id=%s account_id=%s expires_at=%s",
                tenant_id,
                account_id,
                projection.expires_at.isoformat(),
            )
            return cls._build_projection_context(
                account_id=account_id,
                tenant_id=tenant_id,
                role=role,
                tenant_binding=tenant_binding,
                capabilities=projection.capabilities,
                source="stale_projection",
                projection_source_version=projection.source_version,
                projection_expires_at=projection.expires_at,
                stale_projection_used=True,
                refresh_attempted=refresh_attempted,
            )

        # 中文注释：外部托管租户一旦切到 capability 鉴权，就不能在 projection 缺失时
        # 悄悄回退到本地 role；否则会把“外部权威源”重新绕回旧逻辑，造成权限放大。
        return AuthorizationContext(
            account_id=account_id,
            tenant_id=tenant_id,
            role=role,
            management_mode=tenant_binding.management_mode,
            allow_local_member_override=tenant_binding.allow_local_member_override,
            capabilities=[],
            capability_source="external_projection_missing",
            membership_active=membership_active,
            refresh_attempted=refresh_attempted,
        )

    @classmethod
    def _try_refresh_external_context(
        cls,
        *,
        account_id: str,
        tenant_id: str,
        role: TenantAccountRole | None,
        tenant_binding: ExternalTenantBinding,
        account_binding: ExternalAccountBinding,
        now: datetime,
    ) -> AuthorizationContext | None:
        try:
            resolved = ExternalIdentityService.resolve_authorization(
                external_tenant_id=tenant_binding.external_tenant_id,
                external_user_id=account_binding.external_user_id,
            )
        except ExternalBindingNotFoundError:
            logger.warning(
                "external managed workspace missing binding during resolve: tenant_id=%s account_id=%s",
                tenant_id,
                account_id,
            )
            return None
        except Exception:
            logger.exception(
                "failed to resolve external authorization snapshot: tenant_id=%s account_id=%s",
                tenant_id,
                account_id,
            )
            return None

        if not resolved.membership_active:
            return AuthorizationContext(
                account_id=account_id,
                tenant_id=tenant_id,
                role=role,
                management_mode=resolved.management_mode,
                allow_local_member_override=resolved.allow_local_member_override,
                capabilities=[],
                capability_source="external_membership_inactive",
                membership_active=False,
            )

        if resolved.projection_expires_at is not None and resolved.projection_expires_at > now:
            return AuthorizationContext(
                account_id=account_id,
                tenant_id=tenant_id,
                role=role,
                management_mode=resolved.management_mode,
                allow_local_member_override=resolved.allow_local_member_override,
                capabilities=AuthorizationService.normalize_capabilities(resolved.capabilities),
                capability_source="projection_refreshed",
                membership_active=True,
                projection_source_version=resolved.projection_source_version,
                projection_expires_at=resolved.projection_expires_at,
            )

        if (
            resolved.projection_expires_at is not None
            and resolved.projection_expires_at + cls.STALE_PROJECTION_GRACE_PERIOD > now
            and resolved.capabilities
        ):
            logger.warning(
                "using stale resolved projection in grace window: tenant_id=%s account_id=%s expires_at=%s",
                tenant_id,
                account_id,
                resolved.projection_expires_at.isoformat(),
            )
            return AuthorizationContext(
                account_id=account_id,
                tenant_id=tenant_id,
                role=role,
                management_mode=resolved.management_mode,
                allow_local_member_override=resolved.allow_local_member_override,
                capabilities=AuthorizationService.normalize_capabilities(resolved.capabilities),
                capability_source="stale_projection",
                membership_active=True,
                projection_source_version=resolved.projection_source_version,
                projection_expires_at=resolved.projection_expires_at,
                stale_projection_used=True,
            )

        return AuthorizationContext(
            account_id=account_id,
            tenant_id=tenant_id,
            role=role,
            management_mode=resolved.management_mode,
            allow_local_member_override=resolved.allow_local_member_override,
            capabilities=[],
            capability_source="external_projection_expired",
            membership_active=True,
            projection_source_version=resolved.projection_source_version,
            projection_expires_at=resolved.projection_expires_at,
        )

    @classmethod
    def _build_projection_context(
        cls,
        *,
        account_id: str,
        tenant_id: str,
        role: TenantAccountRole | None,
        tenant_binding: ExternalTenantBinding,
        capabilities: list[str],
        source: str,
        projection_source_version: int | None,
        projection_expires_at: datetime | None,
        stale_projection_used: bool = False,
        refresh_attempted: bool = False,
    ) -> AuthorizationContext:
        return AuthorizationContext(
            account_id=account_id,
            tenant_id=tenant_id,
            role=role,
            management_mode=tenant_binding.management_mode,
            allow_local_member_override=tenant_binding.allow_local_member_override,
            capabilities=AuthorizationService.normalize_capabilities(capabilities),
            capability_source=source,
            membership_active=True,
            projection_source_version=projection_source_version,
            projection_expires_at=projection_expires_at,
            stale_projection_used=stale_projection_used,
            refresh_attempted=refresh_attempted,
        )
