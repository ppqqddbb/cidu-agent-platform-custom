"""Unit tests for services.external_identity_service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from configs import dify_config
from models import (
    Account,
    AccountStatus,
    ExternalAccountBinding,
    ExternalManagementMode,
    ExternalMembershipBinding,
    ExternalPermissionProjection,
    ExternalTenantBinding,
    Tenant,
    TenantAccountJoin,
    TenantAccountRole,
    TenantStatus,
)
from services.external_identity_service import ExternalIdentityService


@dataclass
class RecordingSession:
    scalar_results: list[object | None] = field(default_factory=list)
    get_results: list[object | None] = field(default_factory=list)
    added: list[object] = field(default_factory=list)
    deleted: list[object] = field(default_factory=list)
    commit_count: int = 0
    rollback_count: int = 0
    flush_count: int = 0

    def scalar(self, _statement: object) -> object | None:
        if not self.scalar_results:
            raise AssertionError("unexpected scalar() call")
        return self.scalar_results.pop(0)

    def get(self, _model: object, _key: object) -> object | None:
        if not self.get_results:
            raise AssertionError("unexpected get() call")
        return self.get_results.pop(0)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    def flush(self) -> None:
        self.flush_count += 1

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


def _patch_db_session(session: RecordingSession):
    return patch(
        "services.external_identity_service.db",
        SimpleNamespace(session=session),
    )


def _make_tenant_binding(
    *,
    external_tenant_id: str = "tenant-ext",
    tenant_id: str = "tenant-local",
    source_version: int = 3,
    management_mode: ExternalManagementMode = ExternalManagementMode.EXTERNAL_MANAGED,
    allow_local_member_override: bool = False,
) -> ExternalTenantBinding:
    return ExternalTenantBinding(
        external_tenant_id=external_tenant_id,
        tenant_id=tenant_id,
        source_version=source_version,
        management_mode=management_mode,
        allow_local_member_override=allow_local_member_override,
    )


def _make_account_binding(
    *,
    external_user_id: str = "user-ext",
    account_id: str = "account-local",
    source_version: int = 3,
) -> ExternalAccountBinding:
    return ExternalAccountBinding(
        external_user_id=external_user_id,
        account_id=account_id,
        source_version=source_version,
    )


class TestExternalIdentityService:
    @patch("services.external_identity_service.ssrf_proxy.post")
    def test_fetch_external_resolve_payload_returns_validated_payload(self, post_mock) -> None:
        post_mock.return_value = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    "source_version": 12,
                    "membership_active": True,
                    "display_role": "admin",
                    "capabilities": ["workspace.view", "workspace.member.list"],
                    "expires_at": "2030-01-01T00:00:00Z",
                    "management_mode": "external_managed",
                    "allow_local_member_override": True,
                }
            },
        )

        with (
            patch.object(dify_config, "EXTERNAL_INTEGRATION_RESOLVE_ENABLED", True),
            patch.object(dify_config, "EXTERNAL_INTEGRATION_RESOLVE_URL", "https://rbac.example.com/resolve"),
            patch.object(dify_config, "EXTERNAL_INTEGRATION_RESOLVE_API_KEY", "resolve-key"),
            patch.object(dify_config, "EXTERNAL_INTEGRATION_RESOLVE_TIMEOUT", 7.5),
        ):
            payload = ExternalIdentityService._fetch_external_resolve_payload(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
            )

        assert payload is not None
        assert payload.source_version == 12
        assert payload.display_role == TenantAccountRole.ADMIN
        assert payload.allow_local_member_override is True
        assert payload.capabilities == ["workspace.view", "workspace.member.list"]
        post_mock.assert_called_once()
        assert post_mock.call_args.kwargs["timeout"] == 7.5
        assert post_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer resolve-key"

    def test_upsert_tenant_creates_local_tenant_binding_and_event(self) -> None:
        session = RecordingSession(
            scalar_results=[None, None],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.upsert_tenant(
                external_tenant_id="tenant-ext",
                name="External Workspace",
                status=TenantStatus.NORMAL,
                management_mode=ExternalManagementMode.EXTERNAL_MANAGED,
                allow_local_member_override=True,
                source_version=5,
                event_id="evt-tenant-create",
                event_payload={"name": "External Workspace"},
            )

        assert result.applied is True
        assert result.external_tenant_id == "tenant-ext"
        assert session.flush_count == 1
        assert session.commit_count == 1
        assert any(isinstance(obj, Tenant) for obj in session.added)
        assert any(isinstance(obj, ExternalTenantBinding) for obj in session.added)
        assert any(obj.__class__.__name__ == "ExternalSyncInbox" for obj in session.added)

    def test_upsert_user_reuses_existing_account_when_email_matches(self) -> None:
        existing_account = Account(name="Old Name", email="user@example.com")
        existing_account.avatar = "old-avatar"
        existing_account.status = AccountStatus.PENDING

        session = RecordingSession(
            scalar_results=[None, None, existing_account, None],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.upsert_user(
                external_user_id="user-ext",
                email="USER@example.com",
                name="New Name",
                avatar="new-avatar",
                status=AccountStatus.ACTIVE,
                source_version=7,
                event_id="evt-user-upsert",
                event_payload={"email": "USER@example.com"},
            )

        assert result.applied is True
        assert result.account_id == existing_account.id
        assert existing_account.email == "user@example.com"
        assert existing_account.name == "New Name"
        assert existing_account.avatar == "new-avatar"
        assert existing_account.status == AccountStatus.ACTIVE
        assert session.commit_count == 1
        assert any(isinstance(obj, ExternalAccountBinding) for obj in session.added)

    def test_upsert_membership_returns_stale_when_source_version_is_older(self) -> None:
        tenant_binding = _make_tenant_binding(source_version=6)
        account_binding = _make_account_binding(source_version=6)
        membership_binding = ExternalMembershipBinding(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=8,
            display_role=TenantAccountRole.ADMIN,
            is_deleted=False,
        )
        session = RecordingSession(
            scalar_results=[None, tenant_binding, account_binding, membership_binding],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.upsert_membership(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
                display_role=TenantAccountRole.EDITOR,
                source_version=7,
                event_id="evt-membership-stale",
                event_payload={"display_role": "editor"},
            )

        assert result.applied is False
        assert result.reason == "stale_version"
        assert session.commit_count == 1

    def test_upsert_membership_duplicate_event_short_circuits_without_writes(self) -> None:
        session = RecordingSession(
            scalar_results=[object()],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.upsert_membership(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
                display_role=TenantAccountRole.NORMAL,
                source_version=1,
                event_id="evt-duplicate",
            )

        assert result.applied is False
        assert result.reason == "duplicate_event"
        assert session.commit_count == 0
        assert session.added == []

    def test_remove_membership_marks_tombstone_and_deletes_join_and_projection(self) -> None:
        tenant_binding = _make_tenant_binding()
        account_binding = _make_account_binding()
        membership_binding = ExternalMembershipBinding(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=4,
            display_role=TenantAccountRole.ADMIN,
            is_deleted=False,
        )
        join = TenantAccountJoin(
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            role=TenantAccountRole.ADMIN,
        )
        projection = ExternalPermissionProjection(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=4,
            expires_at=datetime(2026, 4, 9, 12, 0, 0),
            capabilities=["workspace.view"],
        )
        session = RecordingSession(
            scalar_results=[None, tenant_binding, account_binding, membership_binding, join, projection],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.remove_membership(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
                source_version=5,
                event_id="evt-membership-delete",
                event_payload={"source_version": 5},
            )

        assert result.applied is True
        assert membership_binding.is_deleted is True
        assert membership_binding.source_version == 5
        assert join in session.deleted
        assert projection in session.deleted
        assert session.commit_count == 1

    def test_replace_authorization_returns_idempotent_for_same_snapshot(self) -> None:
        tenant_binding = _make_tenant_binding()
        account_binding = _make_account_binding()
        membership_binding = ExternalMembershipBinding(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=3,
            display_role=TenantAccountRole.ADMIN,
            is_deleted=False,
        )
        expires_at = datetime(2026, 4, 9, 13, 0, 0)
        projection = ExternalPermissionProjection(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=9,
            expires_at=expires_at,
            capabilities=["workspace.edit", "workspace.view"],
        )
        session = RecordingSession(
            scalar_results=[None, tenant_binding, account_binding, membership_binding, projection],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.replace_authorization(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
                capabilities=["workspace.view", "workspace.edit", "workspace.view"],
                expires_at=expires_at,
                source_version=9,
                event_id="evt-authz-same",
                event_payload={"capabilities": ["workspace.view", "workspace.edit"]},
            )

        assert result.applied is False
        assert result.reason == "idempotent_replay"
        assert result.capabilities == ["workspace.edit", "workspace.view"]
        assert session.commit_count == 1

    def test_resolve_authorization_ignores_projection_for_deleted_membership(self) -> None:
        tenant_binding = _make_tenant_binding(allow_local_member_override=True)
        account_binding = _make_account_binding()
        membership_binding = ExternalMembershipBinding(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=11,
            display_role=TenantAccountRole.ADMIN,
            is_deleted=True,
        )
        projection = ExternalPermissionProjection(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=11,
            expires_at=datetime(2026, 4, 9, 14, 0, 0),
            capabilities=["workspace.member.list"],
        )
        session = RecordingSession(
            scalar_results=[tenant_binding, account_binding, membership_binding, projection],
        )

        with _patch_db_session(session):
            result = ExternalIdentityService.resolve_authorization(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
            )

        assert result.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
        assert result.allow_local_member_override is True
        assert result.membership_active is False
        assert result.display_role is None
        assert result.capabilities == []
        assert result.projection_source_version is None
        assert result.projection_expires_at is None

    def test_resolve_authorization_reloads_snapshot_after_external_sync(self) -> None:
        initial_tenant_binding = _make_tenant_binding(allow_local_member_override=False)
        refreshed_tenant_binding = _make_tenant_binding(allow_local_member_override=True)
        account_binding = _make_account_binding()
        membership_binding = ExternalMembershipBinding(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=refreshed_tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=12,
            display_role=TenantAccountRole.ADMIN,
            is_deleted=False,
        )
        projection = ExternalPermissionProjection(
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            tenant_id=refreshed_tenant_binding.tenant_id,
            account_id=account_binding.account_id,
            source_version=12,
            expires_at=datetime(2030, 1, 1, 0, 0, 0),
            capabilities=["workspace.member.list", "workspace.view"],
        )
        session = RecordingSession(
            scalar_results=[
                initial_tenant_binding,
                account_binding,
                refreshed_tenant_binding,
                account_binding,
                membership_binding,
                projection,
            ],
        )

        with (
            _patch_db_session(session),
            patch(
                "services.external_identity_service.ExternalIdentityService._sync_authorization_projection_from_external_source",
                return_value=True,
            ) as sync_mock,
        ):
            result = ExternalIdentityService.resolve_authorization(
                external_tenant_id="tenant-ext",
                external_user_id="user-ext",
            )

        sync_mock.assert_called_once()
        assert result.allow_local_member_override is True
        assert result.membership_active is True
        assert result.display_role == TenantAccountRole.ADMIN
        assert result.capabilities == ["workspace.member.list", "workspace.view"]
