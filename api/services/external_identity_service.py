"""Service layer for external tenant/account/membership/projection sync.

This module keeps the first integration phase explicit and conservative:

- external IDs map onto local `Tenant` / `Account` / `TenantAccountJoin`
- `source_version` decides freshness
- `event_id` is used only for deduplication and audit
- membership deletes keep tombstones so older events cannot resurrect access

Phase 3 extends `resolve_authorization(...)` with an optional callback mode:

- keep local snapshot reads as the baseline behavior
- when explicitly enabled, pull a latest snapshot from external authority first
- write the refreshed membership/projection back into local tables
- tolerate callback failures by falling back to existing local snapshot behavior
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from configs import dify_config
from core.helper.ssrf_proxy import ssrf_proxy
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models import (
    Account,
    AccountStatus,
    ExternalAccountBinding,
    ExternalManagementMode,
    ExternalMembershipBinding,
    ExternalPermissionProjection,
    ExternalSyncInbox,
    ExternalSyncStatus,
    ExternalTenantBinding,
    Tenant,
    TenantAccountJoin,
    TenantAccountRole,
    TenantStatus,
)
from services.errors.integration import (
    ExternalBindingNotFoundError,
    ExternalIntegrityError,
    IntegrationVersionConflictError,
)

logger = logging.getLogger(__name__)


class ExternalResolvePayload(BaseModel):
    """Payload returned by external resolve callback for one tenant-member scope."""

    source_version: int = Field(ge=0)
    membership_active: bool = True
    display_role: TenantAccountRole | None = None
    capabilities: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    management_mode: ExternalManagementMode = ExternalManagementMode.EXTERNAL_MANAGED
    allow_local_member_override: bool = False

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _ensure_projection_expiry_for_active_membership(self) -> ExternalResolvePayload:
        if self.membership_active and self.expires_at is None:
            raise ValueError("expires_at is required when membership_active is true")
        return self


@dataclass(slots=True)
class IntegrationMutationResult:
    applied: bool
    reason: str | None = None
    tenant_id: str | None = None
    account_id: str | None = None
    external_tenant_id: str | None = None
    external_user_id: str | None = None
    event_id: str | None = None
    capabilities: list[str] = field(default_factory=list)
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "applied": self.applied,
            "reason": self.reason,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "external_tenant_id": self.external_tenant_id,
            "external_user_id": self.external_user_id,
            "event_id": self.event_id,
        }
        if self.capabilities:
            data["capabilities"] = self.capabilities
        if self.expires_at is not None:
            data["expires_at"] = self.expires_at.isoformat() + "Z"
        return data


@dataclass(slots=True)
class IntegrationResolveResult:
    tenant_id: str
    account_id: str
    external_tenant_id: str
    external_user_id: str
    management_mode: ExternalManagementMode
    allow_local_member_override: bool
    membership_active: bool
    display_role: TenantAccountRole | None
    capabilities: list[str]
    projection_source_version: int | None
    projection_expires_at: datetime | None

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "external_tenant_id": self.external_tenant_id,
            "external_user_id": self.external_user_id,
            "management_mode": self.management_mode.value,
            "allow_local_member_override": self.allow_local_member_override,
            "membership_active": self.membership_active,
            "display_role": self.display_role.value if self.display_role is not None else None,
            "capabilities": self.capabilities,
            "projection_source_version": self.projection_source_version,
            "projection_expires_at": self.projection_expires_at.isoformat() + "Z"
            if self.projection_expires_at is not None
            else None,
        }


class ExternalIdentityService:
    """Mutate and read external identity bindings plus capability projections."""

    @staticmethod
    def _normalize_capabilities(capabilities: list[str]) -> list[str]:
        return sorted({capability.strip() for capability in capabilities if capability.strip()})

    @staticmethod
    def _deduplicate_event(event_id: str | None) -> bool:
        if not event_id:
            return False
        existing = db.session.scalar(select(ExternalSyncInbox).where(ExternalSyncInbox.event_id == event_id).limit(1))
        return existing is not None

    @staticmethod
    def _record_event(
        *,
        event_id: str | None,
        event_type: str,
        external_tenant_id: str | None,
        external_user_id: str | None,
        source_version: int,
        status: ExternalSyncStatus,
        payload: dict[str, object] | None,
        error_message: str | None = None,
    ) -> None:
        if not event_id:
            return

        inbox = ExternalSyncInbox(
            event_id=event_id,
            event_type=event_type,
            external_tenant_id=external_tenant_id,
            external_user_id=external_user_id,
            source_version=source_version,
            status=status,
            payload=payload or {},
            error_message=error_message,
            processed_at=naive_utc_now(),
        )
        db.session.add(inbox)

    @staticmethod
    def _build_duplicate_result(
        *,
        event_id: str | None,
        external_tenant_id: str | None = None,
        external_user_id: str | None = None,
    ) -> IntegrationMutationResult:
        return IntegrationMutationResult(
            applied=False,
            reason=ExternalSyncStatus.DUPLICATE_EVENT.value,
            event_id=event_id,
            external_tenant_id=external_tenant_id,
            external_user_id=external_user_id,
        )

    @staticmethod
    def _get_tenant_binding(external_tenant_id: str) -> ExternalTenantBinding:
        binding = db.session.scalar(
            select(ExternalTenantBinding)
            .where(ExternalTenantBinding.external_tenant_id == external_tenant_id)
            .limit(1)
        )
        if binding is None:
            raise ExternalBindingNotFoundError(f"external tenant {external_tenant_id} is not bound")
        return binding

    @staticmethod
    def _get_account_binding(external_user_id: str) -> ExternalAccountBinding:
        binding = db.session.scalar(
            select(ExternalAccountBinding)
            .where(ExternalAccountBinding.external_user_id == external_user_id)
            .limit(1)
        )
        if binding is None:
            raise ExternalBindingNotFoundError(f"external user {external_user_id} is not bound")
        return binding

    @staticmethod
    def _fetch_external_resolve_payload(
        *,
        external_tenant_id: str,
        external_user_id: str,
    ) -> ExternalResolvePayload | None:
        """
        Fetch one latest authorization snapshot from external authority.

        This callback path is optional and guarded by config flags so existing
        self-hosted behavior stays unchanged by default.
        """
        if not dify_config.EXTERNAL_INTEGRATION_RESOLVE_ENABLED:
            return None

        if not dify_config.EXTERNAL_INTEGRATION_RESOLVE_URL:
            logger.warning(
                "external resolve callback is enabled but EXTERNAL_INTEGRATION_RESOLVE_URL is empty"
            )
            return None

        headers = {"Content-Type": "application/json"}
        if dify_config.EXTERNAL_INTEGRATION_RESOLVE_API_KEY:
            headers["Authorization"] = f"Bearer {dify_config.EXTERNAL_INTEGRATION_RESOLVE_API_KEY}"

        try:
            response = ssrf_proxy.post(
                dify_config.EXTERNAL_INTEGRATION_RESOLVE_URL,
                headers=headers,
                json={
                    "external_tenant_id": external_tenant_id,
                    "external_user_id": external_user_id,
                },
                timeout=dify_config.EXTERNAL_INTEGRATION_RESOLVE_TIMEOUT,
                max_retries=0,
            )
        except Exception:
            logger.exception(
                "failed to fetch external resolve snapshot: external_tenant_id=%s external_user_id=%s",
                external_tenant_id,
                external_user_id,
            )
            return None

        if response.status_code >= 400:
            logger.warning(
                "external resolve endpoint returned non-success status: "
                "status_code=%s external_tenant_id=%s external_user_id=%s",
                response.status_code,
                external_tenant_id,
                external_user_id,
            )
            return None

        try:
            response_payload = response.json()
        except ValueError:
            logger.warning(
                "external resolve endpoint returned non-json body: external_tenant_id=%s external_user_id=%s",
                external_tenant_id,
                external_user_id,
            )
            return None

        if not isinstance(response_payload, dict):
            logger.warning(
                "external resolve payload is not an object: external_tenant_id=%s external_user_id=%s",
                external_tenant_id,
                external_user_id,
            )
            return None

        normalized_payload = (
            response_payload["data"]
            if isinstance(response_payload.get("data"), dict)
            else response_payload
        )
        try:
            return ExternalResolvePayload.model_validate(normalized_payload)
        except ValidationError:
            logger.warning(
                "external resolve payload validation failed: external_tenant_id=%s external_user_id=%s",
                external_tenant_id,
                external_user_id,
                exc_info=True,
            )
            return None

    @classmethod
    def _sync_authorization_projection_from_external_source(
        cls,
        *,
        external_tenant_id: str,
        external_user_id: str,
    ) -> bool:
        """
        Pull and apply external snapshot before reading local resolve result.

        Returns whether local snapshot may have changed and should be reloaded.
        """
        payload = cls._fetch_external_resolve_payload(
            external_tenant_id=external_tenant_id,
            external_user_id=external_user_id,
        )
        if payload is None:
            return False

        changed = False
        if payload.membership_active:
            if payload.expires_at is None:
                raise ExternalIntegrityError("external resolve payload for active membership missing expires_at")
            membership_result = cls.upsert_membership(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                display_role=payload.display_role or TenantAccountRole.NORMAL,
                source_version=payload.source_version,
                event_type="authorization.resolve.membership_upsert",
            )
            projection_result = cls.replace_authorization(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                capabilities=payload.capabilities,
                expires_at=payload.expires_at,
                source_version=payload.source_version,
                event_type="authorization.resolve.replace_authorization",
            )
            changed = membership_result.applied or projection_result.applied
        else:
            remove_result = cls.remove_membership(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                source_version=payload.source_version,
                event_type="authorization.resolve.membership_remove",
            )
            changed = remove_result.applied

        tenant_binding = cls._get_tenant_binding(external_tenant_id)
        if (
            tenant_binding.management_mode != payload.management_mode
            or tenant_binding.allow_local_member_override != payload.allow_local_member_override
        ):
            tenant_binding.management_mode = payload.management_mode
            tenant_binding.allow_local_member_override = payload.allow_local_member_override
            tenant_binding.last_synced_at = naive_utc_now()
            try:
                db.session.commit()
                changed = True
            except Exception:
                db.session.rollback()
                raise

        return changed

    @classmethod
    def upsert_tenant(
        cls,
        *,
        external_tenant_id: str,
        name: str,
        status: TenantStatus,
        management_mode: ExternalManagementMode,
        allow_local_member_override: bool,
        source_version: int,
        event_id: str | None = None,
        event_type: str = "tenant.upsert",
        event_payload: dict[str, object] | None = None,
    ) -> IntegrationMutationResult:
        if cls._deduplicate_event(event_id):
            return cls._build_duplicate_result(event_id=event_id, external_tenant_id=external_tenant_id)

        binding = db.session.scalar(
            select(ExternalTenantBinding)
            .where(ExternalTenantBinding.external_tenant_id == external_tenant_id)
            .limit(1)
        )

        try:
            if binding is None:
                tenant = Tenant(name=name)
                tenant.status = status
                db.session.add(tenant)
                db.session.flush()

                binding = ExternalTenantBinding(
                    external_tenant_id=external_tenant_id,
                    tenant_id=tenant.id,
                    source_version=source_version,
                    management_mode=management_mode,
                    allow_local_member_override=allow_local_member_override,
                    last_synced_at=naive_utc_now(),
                )
                db.session.add(binding)
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=external_tenant_id,
                    external_user_id=None,
                    source_version=source_version,
                    status=ExternalSyncStatus.APPLIED,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=True,
                    tenant_id=tenant.id,
                    external_tenant_id=external_tenant_id,
                    event_id=event_id,
                )

            if binding.source_version > source_version:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=external_tenant_id,
                    external_user_id=None,
                    source_version=source_version,
                    status=ExternalSyncStatus.STALE_VERSION,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.STALE_VERSION.value,
                    tenant_id=binding.tenant_id,
                    external_tenant_id=external_tenant_id,
                    event_id=event_id,
                )

            tenant = db.session.get(Tenant, binding.tenant_id)
            if tenant is None:
                raise ExternalIntegrityError(f"missing tenant for binding {external_tenant_id}")

            same_snapshot = (
                binding.source_version == source_version
                and tenant.name == name
                and tenant.status == status
                and binding.management_mode == management_mode
                and binding.allow_local_member_override == allow_local_member_override
            )
            if same_snapshot:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=external_tenant_id,
                    external_user_id=None,
                    source_version=source_version,
                    status=ExternalSyncStatus.IDEMPOTENT_REPLAY,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.IDEMPOTENT_REPLAY.value,
                    tenant_id=tenant.id,
                    external_tenant_id=external_tenant_id,
                    event_id=event_id,
                )

            if binding.source_version == source_version:
                raise IntegrationVersionConflictError("tenant snapshot differs for the same source_version")

            tenant.name = name
            tenant.status = status
            binding.source_version = source_version
            binding.management_mode = management_mode
            binding.allow_local_member_override = allow_local_member_override
            binding.last_synced_at = naive_utc_now()
            cls._record_event(
                event_id=event_id,
                event_type=event_type,
                external_tenant_id=external_tenant_id,
                external_user_id=None,
                source_version=source_version,
                status=ExternalSyncStatus.APPLIED,
                payload=event_payload,
            )
            db.session.commit()
            return IntegrationMutationResult(
                applied=True,
                tenant_id=tenant.id,
                external_tenant_id=external_tenant_id,
                event_id=event_id,
            )
        except Exception:
            db.session.rollback()
            raise

    @classmethod
    def upsert_user(
        cls,
        *,
        external_user_id: str,
        email: str,
        name: str,
        avatar: str | None,
        status: AccountStatus,
        source_version: int,
        event_id: str | None = None,
        event_type: str = "user.upsert",
        event_payload: dict[str, object] | None = None,
    ) -> IntegrationMutationResult:
        if cls._deduplicate_event(event_id):
            return cls._build_duplicate_result(event_id=event_id, external_user_id=external_user_id)

        normalized_email = email.lower()
        binding = db.session.scalar(
            select(ExternalAccountBinding)
            .where(ExternalAccountBinding.external_user_id == external_user_id)
            .limit(1)
        )

        try:
            if binding is None:
                account = db.session.scalar(select(Account).where(Account.email == normalized_email).limit(1))
                if account is None:
                    account = Account(name=name, email=normalized_email)
                    account.avatar = avatar
                    account.status = status
                    db.session.add(account)
                    db.session.flush()
                else:
                    existing_binding = db.session.scalar(
                        select(ExternalAccountBinding)
                        .where(ExternalAccountBinding.account_id == account.id)
                        .limit(1)
                    )
                    if existing_binding is not None:
                        raise ExternalIntegrityError(f"account {account.id} is already bound to another external user")

                    account.name = name
                    account.avatar = avatar
                    account.status = status

                binding = ExternalAccountBinding(
                    external_user_id=external_user_id,
                    account_id=account.id,
                    source_version=source_version,
                    last_synced_at=naive_utc_now(),
                )
                db.session.add(binding)
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=None,
                    external_user_id=external_user_id,
                    source_version=source_version,
                    status=ExternalSyncStatus.APPLIED,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=True,
                    account_id=account.id,
                    external_user_id=external_user_id,
                    event_id=event_id,
                )

            if binding.source_version > source_version:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=None,
                    external_user_id=external_user_id,
                    source_version=source_version,
                    status=ExternalSyncStatus.STALE_VERSION,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.STALE_VERSION.value,
                    account_id=binding.account_id,
                    external_user_id=external_user_id,
                    event_id=event_id,
                )

            account = db.session.get(Account, binding.account_id)
            if account is None:
                raise ExternalIntegrityError(f"missing account for binding {external_user_id}")

            same_snapshot = (
                binding.source_version == source_version
                and account.email == normalized_email
                and account.name == name
                and account.avatar == avatar
                and account.status == status
            )
            if same_snapshot:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=None,
                    external_user_id=external_user_id,
                    source_version=source_version,
                    status=ExternalSyncStatus.IDEMPOTENT_REPLAY,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.IDEMPOTENT_REPLAY.value,
                    account_id=account.id,
                    external_user_id=external_user_id,
                    event_id=event_id,
                )

            if binding.source_version == source_version:
                raise IntegrationVersionConflictError("user snapshot differs for the same source_version")

            account.email = normalized_email
            account.name = name
            account.avatar = avatar
            account.status = status
            binding.source_version = source_version
            binding.last_synced_at = naive_utc_now()
            cls._record_event(
                event_id=event_id,
                event_type=event_type,
                external_tenant_id=None,
                external_user_id=external_user_id,
                source_version=source_version,
                status=ExternalSyncStatus.APPLIED,
                payload=event_payload,
            )
            db.session.commit()
            return IntegrationMutationResult(
                applied=True,
                account_id=account.id,
                external_user_id=external_user_id,
                event_id=event_id,
            )
        except Exception:
            db.session.rollback()
            raise

    @classmethod
    def upsert_membership(
        cls,
        *,
        external_tenant_id: str,
        external_user_id: str,
        display_role: TenantAccountRole,
        source_version: int,
        event_id: str | None = None,
        event_type: str = "membership.upsert",
        event_payload: dict[str, object] | None = None,
    ) -> IntegrationMutationResult:
        """Upsert one tenant membership and keep a tombstone-safe binding snapshot."""
        if cls._deduplicate_event(event_id):
            return cls._build_duplicate_result(
                event_id=event_id,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
            )

        tenant_binding = cls._get_tenant_binding(external_tenant_id)
        account_binding = cls._get_account_binding(external_user_id)
        binding = db.session.scalar(
            select(ExternalMembershipBinding)
            .where(
                ExternalMembershipBinding.external_tenant_id == external_tenant_id,
                ExternalMembershipBinding.external_user_id == external_user_id,
            )
            .limit(1)
        )

        try:
            if binding is not None and binding.source_version > source_version:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    source_version=source_version,
                    status=ExternalSyncStatus.STALE_VERSION,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.STALE_VERSION.value,
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    event_id=event_id,
                )

            if binding is not None and binding.source_version == source_version:
                if not binding.is_deleted and binding.display_role == display_role:
                    cls._record_event(
                        event_id=event_id,
                        event_type=event_type,
                        external_tenant_id=external_tenant_id,
                        external_user_id=external_user_id,
                        source_version=source_version,
                        status=ExternalSyncStatus.IDEMPOTENT_REPLAY,
                        payload=event_payload,
                    )
                    db.session.commit()
                    return IntegrationMutationResult(
                        applied=False,
                        reason=ExternalSyncStatus.IDEMPOTENT_REPLAY.value,
                        tenant_id=tenant_binding.tenant_id,
                        account_id=account_binding.account_id,
                        external_tenant_id=external_tenant_id,
                        external_user_id=external_user_id,
                        event_id=event_id,
                    )
                raise IntegrationVersionConflictError("membership snapshot differs for the same source_version")

            join = db.session.scalar(
                select(TenantAccountJoin)
                .where(
                    TenantAccountJoin.tenant_id == tenant_binding.tenant_id,
                    TenantAccountJoin.account_id == account_binding.account_id,
                )
                .limit(1)
            )
            if join is None:
                join = TenantAccountJoin(
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    role=display_role,
                )
                db.session.add(join)
            else:
                join.role = display_role

            if binding is None:
                binding = ExternalMembershipBinding(
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    source_version=source_version,
                    display_role=display_role,
                    is_deleted=False,
                    last_synced_at=naive_utc_now(),
                )
                db.session.add(binding)
            else:
                binding.tenant_id = tenant_binding.tenant_id
                binding.account_id = account_binding.account_id
                binding.source_version = source_version
                binding.display_role = display_role
                binding.is_deleted = False
                binding.last_synced_at = naive_utc_now()

            cls._record_event(
                event_id=event_id,
                event_type=event_type,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                source_version=source_version,
                status=ExternalSyncStatus.APPLIED,
                payload=event_payload,
            )
            db.session.commit()
            return IntegrationMutationResult(
                applied=True,
                tenant_id=tenant_binding.tenant_id,
                account_id=account_binding.account_id,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                event_id=event_id,
            )
        except Exception:
            db.session.rollback()
            raise

    @classmethod
    def replace_authorization(
        cls,
        *,
        external_tenant_id: str,
        external_user_id: str,
        capabilities: list[str],
        expires_at: datetime,
        source_version: int,
        event_id: str | None = None,
        event_type: str = "authorization.replace",
        event_payload: dict[str, object] | None = None,
    ) -> IntegrationMutationResult:
        """Replace the current capability projection for one active external membership."""
        if cls._deduplicate_event(event_id):
            return cls._build_duplicate_result(
                event_id=event_id,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
            )

        tenant_binding = cls._get_tenant_binding(external_tenant_id)
        account_binding = cls._get_account_binding(external_user_id)
        membership_binding = db.session.scalar(
            select(ExternalMembershipBinding)
            .where(
                ExternalMembershipBinding.external_tenant_id == external_tenant_id,
                ExternalMembershipBinding.external_user_id == external_user_id,
                ExternalMembershipBinding.is_deleted.is_(False),
            )
            .limit(1)
        )
        if membership_binding is None:
            raise ExternalBindingNotFoundError("active membership binding not found for authorization update")

        normalized_capabilities = cls._normalize_capabilities(capabilities)
        projection = db.session.scalar(
            select(ExternalPermissionProjection)
            .where(
                ExternalPermissionProjection.external_tenant_id == external_tenant_id,
                ExternalPermissionProjection.external_user_id == external_user_id,
            )
            .limit(1)
        )

        try:
            if projection is not None and projection.source_version > source_version:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    source_version=source_version,
                    status=ExternalSyncStatus.STALE_VERSION,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.STALE_VERSION.value,
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    event_id=event_id,
                )

            if projection is not None and projection.source_version == source_version:
                same_projection = (
                    cls._normalize_capabilities(projection.capabilities) == normalized_capabilities
                    and projection.expires_at == expires_at
                )
                if same_projection:
                    cls._record_event(
                        event_id=event_id,
                        event_type=event_type,
                        external_tenant_id=external_tenant_id,
                        external_user_id=external_user_id,
                        source_version=source_version,
                        status=ExternalSyncStatus.IDEMPOTENT_REPLAY,
                        payload=event_payload,
                    )
                    db.session.commit()
                    return IntegrationMutationResult(
                        applied=False,
                        reason=ExternalSyncStatus.IDEMPOTENT_REPLAY.value,
                        tenant_id=tenant_binding.tenant_id,
                        account_id=account_binding.account_id,
                        external_tenant_id=external_tenant_id,
                        external_user_id=external_user_id,
                        event_id=event_id,
                        capabilities=normalized_capabilities,
                        expires_at=expires_at,
                    )
                raise IntegrationVersionConflictError("authorization snapshot differs for the same source_version")

            if projection is None:
                projection = ExternalPermissionProjection(
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    capabilities=normalized_capabilities,
                    source_version=source_version,
                    expires_at=expires_at,
                    last_synced_at=naive_utc_now(),
                )
                db.session.add(projection)
            else:
                projection.tenant_id = tenant_binding.tenant_id
                projection.account_id = account_binding.account_id
                projection.capabilities = normalized_capabilities
                projection.source_version = source_version
                projection.expires_at = expires_at
                projection.last_synced_at = naive_utc_now()

            cls._record_event(
                event_id=event_id,
                event_type=event_type,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                source_version=source_version,
                status=ExternalSyncStatus.APPLIED,
                payload=event_payload,
            )
            db.session.commit()
            return IntegrationMutationResult(
                applied=True,
                tenant_id=tenant_binding.tenant_id,
                account_id=account_binding.account_id,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                event_id=event_id,
                capabilities=normalized_capabilities,
                expires_at=expires_at,
            )
        except Exception:
            db.session.rollback()
            raise

    @classmethod
    def resolve_authorization(
        cls,
        *,
        external_tenant_id: str,
        external_user_id: str,
    ) -> IntegrationResolveResult:
        """Return the local snapshot for one external tenant member.

        Resolve always works with local bindings/projections as final source for
        the authz context. When external callback is enabled, we first try to
        refresh local projection from external authority, then read the updated
        local snapshot.
        """
        tenant_binding = cls._get_tenant_binding(external_tenant_id)
        account_binding = cls._get_account_binding(external_user_id)

        try:
            local_snapshot_changed = cls._sync_authorization_projection_from_external_source(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
            )
        except Exception:
            logger.exception(
                "failed to sync authorization projection from external source before resolve: "
                "external_tenant_id=%s external_user_id=%s",
                external_tenant_id,
                external_user_id,
            )
            local_snapshot_changed = False

        if local_snapshot_changed:
            tenant_binding = cls._get_tenant_binding(external_tenant_id)
            account_binding = cls._get_account_binding(external_user_id)

        membership_binding = db.session.scalar(
            select(ExternalMembershipBinding)
            .where(
                ExternalMembershipBinding.external_tenant_id == external_tenant_id,
                ExternalMembershipBinding.external_user_id == external_user_id,
            )
            .limit(1)
        )
        projection = db.session.scalar(
            select(ExternalPermissionProjection)
            .where(
                ExternalPermissionProjection.external_tenant_id == external_tenant_id,
                ExternalPermissionProjection.external_user_id == external_user_id,
            )
            .limit(1)
        )

        membership_active = membership_binding is not None and not membership_binding.is_deleted
        display_role = membership_binding.display_role if membership_active and membership_binding is not None else None
        capabilities = cls._normalize_capabilities(projection.capabilities) if membership_active and projection else []
        projection_source_version = projection.source_version if membership_active and projection is not None else None
        projection_expires_at = projection.expires_at if membership_active and projection is not None else None

        return IntegrationResolveResult(
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            external_tenant_id=external_tenant_id,
            external_user_id=external_user_id,
            management_mode=tenant_binding.management_mode,
            allow_local_member_override=tenant_binding.allow_local_member_override,
            membership_active=membership_active,
            display_role=display_role,
            capabilities=capabilities,
            projection_source_version=projection_source_version,
            projection_expires_at=projection_expires_at,
        )

    @classmethod
    def remove_membership(
        cls,
        *,
        external_tenant_id: str,
        external_user_id: str,
        source_version: int,
        event_id: str | None = None,
        event_type: str = "membership.delete",
        event_payload: dict[str, object] | None = None,
    ) -> IntegrationMutationResult:
        """Remove one membership, delete the join/projection, and leave a tombstone binding."""
        if cls._deduplicate_event(event_id):
            return cls._build_duplicate_result(
                event_id=event_id,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
            )

        tenant_binding = cls._get_tenant_binding(external_tenant_id)
        account_binding = cls._get_account_binding(external_user_id)
        binding = db.session.scalar(
            select(ExternalMembershipBinding)
            .where(
                ExternalMembershipBinding.external_tenant_id == external_tenant_id,
                ExternalMembershipBinding.external_user_id == external_user_id,
            )
            .limit(1)
        )
        try:
            if binding is not None and binding.source_version > source_version:
                cls._record_event(
                    event_id=event_id,
                    event_type=event_type,
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    source_version=source_version,
                    status=ExternalSyncStatus.STALE_VERSION,
                    payload=event_payload,
                )
                db.session.commit()
                return IntegrationMutationResult(
                    applied=False,
                    reason=ExternalSyncStatus.STALE_VERSION.value,
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    event_id=event_id,
                )

            if binding is not None and binding.source_version == source_version:
                if binding.is_deleted:
                    cls._record_event(
                        event_id=event_id,
                        event_type=event_type,
                        external_tenant_id=external_tenant_id,
                        external_user_id=external_user_id,
                        source_version=source_version,
                        status=ExternalSyncStatus.IDEMPOTENT_REPLAY,
                        payload=event_payload,
                    )
                    db.session.commit()
                    return IntegrationMutationResult(
                        applied=False,
                        reason=ExternalSyncStatus.IDEMPOTENT_REPLAY.value,
                        tenant_id=tenant_binding.tenant_id,
                        account_id=account_binding.account_id,
                        external_tenant_id=external_tenant_id,
                        external_user_id=external_user_id,
                        event_id=event_id,
                    )
                raise IntegrationVersionConflictError("membership delete conflicts with active membership snapshot")

            join = db.session.scalar(
                select(TenantAccountJoin)
                .where(
                    TenantAccountJoin.tenant_id == tenant_binding.tenant_id,
                    TenantAccountJoin.account_id == account_binding.account_id,
                )
                .limit(1)
            )
            if join is not None:
                db.session.delete(join)

            projection = db.session.scalar(
                select(ExternalPermissionProjection)
                .where(
                    ExternalPermissionProjection.tenant_id == tenant_binding.tenant_id,
                    ExternalPermissionProjection.account_id == account_binding.account_id,
                )
                .limit(1)
            )
            if projection is not None:
                db.session.delete(projection)

            tombstone_role = binding.display_role if binding is not None else TenantAccountRole.NORMAL
            if binding is None:
                binding = ExternalMembershipBinding(
                    external_tenant_id=external_tenant_id,
                    external_user_id=external_user_id,
                    tenant_id=tenant_binding.tenant_id,
                    account_id=account_binding.account_id,
                    source_version=source_version,
                    display_role=tombstone_role,
                    is_deleted=True,
                    last_synced_at=naive_utc_now(),
                )
                db.session.add(binding)
            else:
                binding.source_version = source_version
                binding.is_deleted = True
                binding.last_synced_at = naive_utc_now()

            cls._record_event(
                event_id=event_id,
                event_type=event_type,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                source_version=source_version,
                status=ExternalSyncStatus.APPLIED,
                payload=event_payload,
            )
            db.session.commit()
            return IntegrationMutationResult(
                applied=True,
                tenant_id=tenant_binding.tenant_id,
                account_id=account_binding.account_id,
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                event_id=event_id,
            )
        except Exception:
            db.session.rollback()
            raise
