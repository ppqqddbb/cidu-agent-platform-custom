from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from models import ExternalManagementMode, TenantAccountRole
from services.authz import AuthzContextService


def test_should_fallback_to_legacy_role_capabilities_for_local_managed_tenant():
    with patch.object(AuthzContextService, "_get_tenant_binding", return_value=None):
        context = AuthzContextService.get_context(
            account_id="account-1",
            tenant_id="tenant-1",
            role=TenantAccountRole.ADMIN,
        )

    assert context.management_mode == ExternalManagementMode.LOCAL_MANAGED
    assert context.capability_source == "legacy_role"
    assert "workspace.member.invite" in context.capabilities
    assert "workspace.member.remove" in context.capabilities
    assert "workspace.member.role.update" in context.capabilities
    assert "workspace.owner.transfer" not in context.capabilities


def test_should_use_fresh_external_projection_when_available():
    now = datetime(2026, 4, 9, 12, 0, 0)
    tenant_binding = SimpleNamespace(
        management_mode=ExternalManagementMode.EXTERNAL_MANAGED,
        allow_local_member_override=False,
        external_tenant_id="ext-tenant-1",
    )
    account_binding = SimpleNamespace(external_user_id="ext-user-1")
    membership_binding = SimpleNamespace(is_deleted=False)
    projection = SimpleNamespace(
        capabilities=["workspace.member.list", "workspace.member.invite"],
        source_version=7,
        expires_at=now + timedelta(minutes=10),
    )

    with (
        patch.object(AuthzContextService, "_get_tenant_binding", return_value=tenant_binding),
        patch.object(AuthzContextService, "_get_account_binding", return_value=account_binding),
        patch.object(AuthzContextService, "_get_membership_binding", return_value=membership_binding),
        patch.object(AuthzContextService, "_get_projection", return_value=projection),
        patch("services.authz.authz_context_service.naive_utc_now", return_value=now),
        patch("services.authz.authz_context_service.ExternalIdentityService.resolve_authorization") as resolve_mock,
    ):
        context = AuthzContextService.get_context(
            account_id="account-1",
            tenant_id="tenant-1",
            role=TenantAccountRole.NORMAL,
        )

    assert context.capability_source == "projection"
    assert context.capabilities == ["workspace.member.invite", "workspace.member.list"]
    assert context.projection_source_version == 7
    resolve_mock.assert_not_called()


def test_should_use_stale_projection_during_grace_window_when_refresh_fails():
    now = datetime(2026, 4, 9, 12, 0, 0)
    tenant_binding = SimpleNamespace(
        management_mode=ExternalManagementMode.EXTERNAL_MANAGED,
        allow_local_member_override=True,
        external_tenant_id="ext-tenant-1",
    )
    account_binding = SimpleNamespace(external_user_id="ext-user-1")
    membership_binding = SimpleNamespace(is_deleted=False)
    projection = SimpleNamespace(
        capabilities=["workspace.member.invite", "workspace.member.list"],
        source_version=9,
        expires_at=now - timedelta(minutes=1),
    )

    with (
        patch.object(AuthzContextService, "_get_tenant_binding", return_value=tenant_binding),
        patch.object(AuthzContextService, "_get_account_binding", return_value=account_binding),
        patch.object(AuthzContextService, "_get_membership_binding", return_value=membership_binding),
        patch.object(AuthzContextService, "_get_projection", return_value=projection),
        patch("services.authz.authz_context_service.naive_utc_now", return_value=now),
        patch(
            "services.authz.authz_context_service.ExternalIdentityService.resolve_authorization",
            side_effect=RuntimeError("resolve failed"),
        ),
    ):
        context = AuthzContextService.get_context(
            account_id="account-1",
            tenant_id="tenant-1",
            role=TenantAccountRole.ADMIN,
        )

    assert context.capability_source == "stale_projection"
    assert context.stale_projection_used is True
    assert context.refresh_attempted is True
    assert "workspace.member.invite" in context.capabilities


def test_should_not_fallback_to_role_when_external_projection_is_missing():
    tenant_binding = SimpleNamespace(
        management_mode=ExternalManagementMode.EXTERNAL_MANAGED,
        allow_local_member_override=False,
        external_tenant_id="ext-tenant-1",
    )

    with (
        patch.object(AuthzContextService, "_get_tenant_binding", return_value=tenant_binding),
        patch.object(AuthzContextService, "_get_account_binding", return_value=None),
        patch.object(AuthzContextService, "_get_membership_binding", return_value=None),
        patch.object(AuthzContextService, "_get_projection", return_value=None),
        patch.object(AuthzContextService, "_is_super_admin_account", return_value=False),
    ):
        context = AuthzContextService.get_context(
            account_id="account-1",
            tenant_id="tenant-1",
            role=TenantAccountRole.OWNER,
        )

    assert context.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
    assert context.capability_source == "external_projection_missing"
    assert context.capabilities == []


def test_should_fallback_to_role_for_super_admin_when_external_binding_is_missing():
    tenant_binding = SimpleNamespace(
        management_mode=ExternalManagementMode.EXTERNAL_MANAGED,
        allow_local_member_override=False,
        external_tenant_id="ext-tenant-1",
    )

    with (
        patch.object(AuthzContextService, "_get_tenant_binding", return_value=tenant_binding),
        patch.object(AuthzContextService, "_get_account_binding", return_value=None),
        patch.object(AuthzContextService, "_get_membership_binding", return_value=None),
        patch.object(AuthzContextService, "_get_projection", return_value=None),
        patch.object(AuthzContextService, "_is_super_admin_account", return_value=True),
    ):
        context = AuthzContextService.get_context(
            account_id="account-1",
            tenant_id="tenant-1",
            role=TenantAccountRole.ADMIN,
        )

    assert context.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
    assert context.capability_source == "super_admin_legacy_fallback"
    assert "workspace.member.invite" in context.capabilities
    assert "workspace.member.remove" in context.capabilities
    assert "workspace.member.role.update" in context.capabilities
