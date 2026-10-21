from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden

from controllers.console.workspace.tenant_management import (
    TenantManagementApi,
    TenantManagementSyncApi,
    TenantManagementTenantsApi,
)


def unwrap(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


class TestTenantManagementApi:
    def test_get_returns_local_managed_when_external_binding_absent(self, app):
        api = TenantManagementApi()
        method = unwrap(api.get)

        with (
            app.test_request_context("/workspaces/current/tenant-management"),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.tenant_management.db.session.scalar", return_value=None),
        ):
            result, status = method(api)

        assert status == 200
        assert result["tenant_id"] == "tenant-1"
        assert result["management_mode"] == "local_managed"
        assert result["allow_local_member_override"] is False
        assert result["has_external_binding"] is False
        assert result["external_tenant_binding"] is None

    def test_post_creates_external_binding_when_switching_to_external_managed(self, app):
        api = TenantManagementApi()
        method = unwrap(api.post)

        fake_session = MagicMock()
        fake_session.scalar.side_effect = [None, None]

        with (
            app.test_request_context(
                "/workspaces/current/tenant-management",
                method="POST",
                json={
                    "management_mode": "external_managed",
                    "allow_local_member_override": True,
                    "external_tenant_id": "tenant-ext-1",
                },
            ),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.tenant_management.TenantService.get_default_tenant",
                return_value=SimpleNamespace(id="tenant-default"),
            ),
            patch("controllers.console.workspace.tenant_management.db.session", fake_session),
            patch(
                "controllers.console.workspace.tenant_management._build_tenant_management_response",
                return_value={
                    "tenant_id": "tenant-1",
                    "management_mode": "external_managed",
                    "allow_local_member_override": True,
                    "has_external_binding": True,
                    "external_tenant_binding": {
                        "external_tenant_id": "tenant-ext-1",
                        "source_version": 0,
                        "last_synced_at": 1712736000,
                    },
                },
            ),
        ):
            result, status = method(api)

        assert status == 200
        assert result["result"] == "success"
        assert result["tenant_management"]["management_mode"] == "external_managed"
        fake_session.add.assert_called_once()
        added_binding = fake_session.add.call_args.args[0]
        assert added_binding.external_tenant_id == "tenant-ext-1"
        assert added_binding.tenant_id == "tenant-1"
        assert added_binding.source_version == 0
        assert added_binding.allow_local_member_override is True
        fake_session.commit.assert_called_once()

    def test_post_requires_external_tenant_id_when_enabling_external_managed(self, app):
        api = TenantManagementApi()
        method = unwrap(api.post)

        fake_session = MagicMock()
        fake_session.scalar.return_value = None

        with (
            app.test_request_context(
                "/workspaces/current/tenant-management",
                method="POST",
                json={
                    "management_mode": "external_managed",
                    "allow_local_member_override": False,
                },
            ),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.tenant_management.db.session", fake_session),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 400

    def test_post_rejects_external_managed_for_default_tenant(self, app):
        api = TenantManagementApi()
        method = unwrap(api.post)

        fake_session = MagicMock()
        default_tenant = SimpleNamespace(id="tenant-1")

        with (
            app.test_request_context(
                "/workspaces/current/tenant-management",
                method="POST",
                json={
                    "management_mode": "external_managed",
                    "allow_local_member_override": False,
                    "external_tenant_id": "tenant-ext-1",
                },
            ),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.tenant_management.TenantService.get_default_tenant",
                return_value=default_tenant,
            ),
            patch("controllers.console.workspace.tenant_management.db.session", fake_session),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 400
        fake_session.add.assert_not_called()
        fake_session.commit.assert_not_called()

    def test_get_forbidden_when_not_super_admin(self, app):
        api = TenantManagementApi()
        method = unwrap(api.get)

        with (
            app.test_request_context("/workspaces/current/tenant-management"),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                side_effect=Forbidden("Super admin permission required."),
            ),
        ):
            with pytest.raises(Forbidden):
                method(api)

    def test_post_forbidden_when_not_super_admin(self, app):
        api = TenantManagementApi()
        method = unwrap(api.post)

        with (
            app.test_request_context(
                "/workspaces/current/tenant-management",
                method="POST",
                json={
                    "management_mode": "local_managed",
                    "allow_local_member_override": False,
                },
            ),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                side_effect=Forbidden("Super admin permission required."),
            ),
        ):
            with pytest.raises(Forbidden):
                method(api)


class TestTenantManagementSyncApi:
    def test_post_sync_returns_resolve_result(self, app):
        api = TenantManagementSyncApi()
        method = unwrap(api.post)

        tenant_binding = SimpleNamespace(external_tenant_id="tenant-ext-1")
        account_binding = SimpleNamespace(external_user_id="user-ext-1")
        fake_result = SimpleNamespace(to_dict=lambda: {"capabilities": ["workspace.view"], "membership_active": True})

        with (
            app.test_request_context("/workspaces/current/tenant-management/sync", method="POST"),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.tenant_management.db.session.scalar",
                side_effect=[tenant_binding, account_binding],
            ),
            patch(
                "controllers.console.workspace.tenant_management.ExternalIdentityService.resolve_authorization",
                return_value=fake_result,
            ) as resolve_mock,
        ):
            result, status = method(api)

        assert status == 200
        assert result["result"] == "success"
        assert result["resolve"]["membership_active"] is True
        resolve_mock.assert_called_once_with(
            external_tenant_id="tenant-ext-1",
            external_user_id="user-ext-1",
        )

    def test_post_forbidden_when_not_super_admin(self, app):
        api = TenantManagementSyncApi()
        method = unwrap(api.post)

        with (
            app.test_request_context("/workspaces/current/tenant-management/sync", method="POST"),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                side_effect=Forbidden("Super admin permission required."),
            ),
        ):
            with pytest.raises(Forbidden):
                method(api)


class TestTenantManagementTenantsApi:
    def test_get_returns_all_tenants_for_super_admin(self, app):
        api = TenantManagementTenantsApi()
        method = unwrap(api.get)

        tenant_default = SimpleNamespace(
            id="tenant-default",
            name="Default Tenant",
            status=SimpleNamespace(value="normal"),
            created_at=None,
        )
        tenant_other = SimpleNamespace(
            id="tenant-other",
            name="Other Tenant",
            status=SimpleNamespace(value="normal"),
            created_at=None,
        )
        binding_other = SimpleNamespace(
            tenant_id="tenant-other",
            external_tenant_id="ext-tenant-2",
            management_mode=SimpleNamespace(value="external_managed"),
            allow_local_member_override=True,
        )

        fake_session = MagicMock()
        fake_session.scalars.side_effect = [
            MagicMock(all=MagicMock(return_value=[tenant_default, tenant_other])),
            MagicMock(all=MagicMock(return_value=[binding_other])),
        ]
        fake_session.execute.return_value = [
            ("tenant-default", 1),
            ("tenant-other", 2),
        ]

        with (
            app.test_request_context("/workspaces/tenant-management/tenants"),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-1"), "tenant-default"),
            ),
            patch("controllers.console.workspace.tenant_management.db.session", fake_session),
            patch(
                "controllers.console.workspace.tenant_management.TenantService.get_default_tenant",
                return_value=tenant_default,
            ),
        ):
            result, status = method(api)

        assert status == 200
        assert len(result["tenants"]) == 2
        first, second = result["tenants"]
        assert first["id"] == "tenant-default"
        assert first["is_default_tenant"] is True
        assert first["management_mode"] == "local_managed"
        assert second["id"] == "tenant-other"
        assert second["is_default_tenant"] is False
        assert second["management_mode"] == "external_managed"
        assert second["external_tenant_id"] == "ext-tenant-2"
        assert second["member_count"] == 2

    def test_get_forbidden_when_not_super_admin(self, app):
        api = TenantManagementTenantsApi()
        method = unwrap(api.get)

        with (
            app.test_request_context("/workspaces/tenant-management/tenants"),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                side_effect=Forbidden("Super admin permission required."),
            ),
        ):
            with pytest.raises(Forbidden):
                method(api)

    def test_post_creates_tenant_for_super_admin(self, app):
        api = TenantManagementTenantsApi()
        method = unwrap(api.post)

        created_tenant = SimpleNamespace(
            id="tenant-new",
            name="Tenant New",
            status=SimpleNamespace(value="normal"),
            created_at=None,
        )
        default_tenant = SimpleNamespace(id="tenant-default")
        fake_session = MagicMock()
        fake_session.scalar.side_effect = [
            None,  # created binding
            0,  # member count
        ]

        with (
            app.test_request_context(
                "/workspaces/tenant-management/tenants",
                method="POST",
                json={
                    "name": "Tenant New",
                    "management_mode": "local_managed",
                    "allow_local_member_override": False,
                },
            ),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                return_value=(MagicMock(id="account-super"), "tenant-default"),
            ),
            patch("controllers.console.workspace.tenant_management.db.session", fake_session),
            patch(
                "controllers.console.workspace.tenant_management.TenantService.create_tenant",
                return_value=created_tenant,
            ) as create_tenant_mock,
            patch(
                "controllers.console.workspace.tenant_management.TenantService.get_default_tenant",
                return_value=default_tenant,
            ),
        ):
            result, status = method(api)

        assert status == 201
        assert result["result"] == "success"
        assert result["tenant"]["id"] == "tenant-new"
        assert result["tenant"]["is_default_tenant"] is False
        create_tenant_mock.assert_called_once_with(name="Tenant New", is_from_dashboard=True)
        assert result["tenant"]["member_count"] == 0

    def test_post_forbidden_when_not_super_admin(self, app):
        api = TenantManagementTenantsApi()
        method = unwrap(api.post)

        with (
            app.test_request_context(
                "/workspaces/tenant-management/tenants",
                method="POST",
                json={"name": "Tenant New"},
            ),
            patch(
                "controllers.console.workspace.tenant_management._ensure_super_admin",
                side_effect=Forbidden("Super admin permission required."),
            ),
        ):
            with pytest.raises(Forbidden):
                method(api)
