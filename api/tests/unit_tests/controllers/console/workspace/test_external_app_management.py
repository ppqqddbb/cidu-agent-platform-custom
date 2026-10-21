from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controllers.console.workspace.external_app_management import (
    ExternalAppApiListApi,
    ExternalAppGovernanceCredentialAlertsApi,
    ExternalAppGovernanceRiskReportApi,
    ExternalAppListApi,
    ExternalAppOpenAPIImportApi,
)


def unwrap(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


class TestExternalAppListApi:
    def test_get_returns_apps_with_api_count(self, app):
        api = ExternalAppListApi()
        method = unwrap(api.get)

        app_one = SimpleNamespace(
            id="app-1",
            tenant_id="tenant-1",
            name="CRM",
            description="crm system",
            app_purpose="customer data",
            auth_mode=SimpleNamespace(value="none"),
            auth_config={},
            is_enabled=True,
            created_at=None,
            updated_at=None,
        )
        app_two = SimpleNamespace(
            id="app-2",
            tenant_id="tenant-1",
            name="ERP",
            description="erp system",
            app_purpose="order data",
            auth_mode=SimpleNamespace(value="static_bearer"),
            auth_config={"token": "***"},
            is_enabled=True,
            created_at=None,
            updated_at=None,
        )

        fake_session = MagicMock()
        fake_session.scalar.return_value = 2
        fake_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[app_one, app_two]))
        fake_session.execute.return_value = [("app-1", 3)]

        with (
            app.test_request_context("/workspaces/current/external-apps"),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            result, status = method(api)

        assert status == 200
        assert len(result["apps"]) == 2
        assert result["apps"][0]["id"] == "app-1"
        assert result["apps"][0]["api_count"] == 3
        assert result["apps"][0]["call_mode"] == "gateway"
        assert result["apps"][1]["id"] == "app-2"
        assert result["apps"][1]["api_count"] == 0
        assert result["apps"][1]["call_mode"] == "gateway"
        assert result["pagination"] == {
            "page": 1,
            "page_size": 20,
            "total": 2,
            "has_more": False,
        }

    def test_get_rejects_invalid_pagination_params(self, app):
        api = ExternalAppListApi()
        method = unwrap(api.get)

        with (
            app.test_request_context("/workspaces/current/external-apps?page=0&page_size=10"),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 400

    def test_post_creates_external_app(self, app):
        api = ExternalAppListApi()
        method = unwrap(api.post)

        fake_session = MagicMock()
        fake_session.scalar.return_value = None

        with (
            app.test_request_context(
                "/workspaces/current/external-apps",
                method="POST",
                json={
                    "name": "  CRM App  ",
                    "description": "crm description",
                    "app_purpose": "query orders",
                    "call_mode": "direct",
                    "auth_mode": "none",
                    "auth_config": {},
                    "is_enabled": True,
                },
            ),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            result, status = method(api)

        assert status == 201
        assert result["result"] == "success"
        fake_session.add.assert_called_once()
        created = fake_session.add.call_args.args[0]
        assert created.tenant_id == "tenant-1"
        assert created.name == "CRM App"
        assert created.auth_config["call_mode"] == "direct"
        fake_session.commit.assert_called_once()

    def test_post_rejects_duplicate_name(self, app):
        api = ExternalAppListApi()
        method = unwrap(api.post)

        fake_session = MagicMock()
        fake_session.scalar.return_value = SimpleNamespace(id="existing-app")

        with (
            app.test_request_context(
                "/workspaces/current/external-apps",
                method="POST",
                json={
                    "name": "CRM App",
                    "auth_mode": "none",
                    "auth_config": {},
                },
            ),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 409
        fake_session.add.assert_not_called()


class TestExternalAppOpenAPIImportApi:
    def test_openapi_import_creates_new_api(self, app):
        api = ExternalAppOpenAPIImportApi()
        method = unwrap(api.post)

        fake_session = MagicMock()
        fake_session.scalar.return_value = None

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/app-1/openapi/import",
                method="POST",
                json={
                    "spec": {
                        "openapi": "3.0.0",
                        "paths": {
                            "/orders": {
                                "get": {
                                    "operationId": "listOrders",
                                    "summary": "List orders",
                                    "responses": {
                                        "200": {"description": "ok"},
                                    },
                                },
                            },
                        },
                    },
                },
            ),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_management._get_external_app_or_404",
                return_value=SimpleNamespace(id="app-1", tenant_id="tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            result, status = method(api, "app-1")

        assert status == 200
        assert result["result"] == "success"
        assert result["summary"]["created"] == 1
        assert result["summary"]["updated"] == 0
        fake_session.add.assert_called_once()
        imported_api = fake_session.add.call_args.args[0]
        assert imported_api.source.value == "openapi_import"
        assert imported_api.is_confirmed is False
        fake_session.commit.assert_called_once()

    def test_openapi_import_rejects_spec_without_paths(self, app):
        api = ExternalAppOpenAPIImportApi()
        method = unwrap(api.post)

        fake_session = MagicMock()

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/app-1/openapi/import",
                method="POST",
                json={
                    "spec": {
                        "openapi": "3.0.0",
                    },
                },
            ),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_management._get_external_app_or_404",
                return_value=SimpleNamespace(id="app-1", tenant_id="tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api, "app-1")

        assert exc_info.value.code == 400
        fake_session.add.assert_not_called()


class TestExternalAppApiListApi:
    def test_get_returns_paginated_apis(self, app):
        api = ExternalAppApiListApi()
        method = unwrap(api.get)

        api_one = SimpleNamespace(
            id="api-1",
            tenant_id="tenant-1",
            app_id="app-1",
            name="List Orders",
            http_method="GET",
            path="/orders",
            summary="list",
            description="desc",
            api_purpose="query orders",
            source=SimpleNamespace(value="manual"),
            source_version=1,
            required_permissions=[],
            request_schema={},
            response_schema={},
            is_confirmed=True,
            is_enabled=True,
            imported_at=None,
            created_at=None,
            updated_at=None,
        )
        api_two = SimpleNamespace(
            id="api-2",
            tenant_id="tenant-1",
            app_id="app-1",
            name="Get Order",
            http_method="GET",
            path="/orders/{id}",
            summary="get",
            description="desc",
            api_purpose="query order",
            source=SimpleNamespace(value="manual"),
            source_version=1,
            required_permissions=["order.read"],
            request_schema={},
            response_schema={},
            is_confirmed=True,
            is_enabled=True,
            imported_at=None,
            created_at=None,
            updated_at=None,
        )

        fake_session = MagicMock()
        fake_session.scalar.return_value = 5
        fake_session.scalars.return_value = MagicMock(all=MagicMock(return_value=[api_one, api_two]))

        with (
            app.test_request_context("/workspaces/current/external-apps/app-1/apis?page=2&page_size=2"),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_management._get_external_app_or_404",
                return_value=SimpleNamespace(id="app-1", tenant_id="tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            result, status = method(api, "app-1")

        assert status == 200
        assert len(result["apis"]) == 2
        assert result["apis"][0]["id"] == "api-1"
        assert result["pagination"] == {
            "page": 2,
            "page_size": 2,
            "total": 5,
            "has_more": True,
        }


class TestExternalAppGovernanceRiskReportApi:
    def test_get_returns_gateway_only_recommendations(self, app):
        api = ExternalAppGovernanceRiskReportApi()
        method = unwrap(api.get)

        direct_app = SimpleNamespace(
            id="app-1",
            tenant_id="tenant-1",
            name="ERP",
            auth_config={"call_mode": "direct"},
            created_at=None,
        )
        gateway_app = SimpleNamespace(
            id="app-2",
            tenant_id="tenant-1",
            name="CRM",
            auth_config={"call_mode": "gateway"},
            created_at=None,
        )
        api_direct_high_risk = SimpleNamespace(
            id="api-1",
            tenant_id="tenant-1",
            app_id="app-1",
            name="Update Order",
            http_method="PATCH",
            path="/orders/{id}",
            required_permissions=["order.write"],
            is_confirmed=True,
        )
        api_gateway_non_recommend = SimpleNamespace(
            id="api-2",
            tenant_id="tenant-1",
            app_id="app-2",
            name="List Customer",
            http_method="GET",
            path="/customers",
            required_permissions=["customer.read"],
            is_confirmed=True,
        )

        fake_session = MagicMock()
        fake_session.scalars.side_effect = [
            MagicMock(all=MagicMock(return_value=[direct_app, gateway_app])),
            MagicMock(all=MagicMock(return_value=[api_direct_high_risk, api_gateway_non_recommend])),
        ]

        with (
            app.test_request_context("/workspaces/current/external-apps/governance/risk-report", method="GET"),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            result, status = method(api)

        assert status == 200
        assert result["summary"]["total_apps"] == 2
        assert result["summary"]["total_apis"] == 2
        assert result["summary"]["direct_mode_apps"] == 1
        assert result["summary"]["high_risk_api_candidates"] == 2
        assert result["summary"]["gateway_only_recommendations"] == 1
        assert result["gateway_only_recommendations"][0]["app_id"] == "app-1"
        assert result["gateway_only_recommendations"][0]["recommended_call_mode"] == "gateway"


class TestExternalAppGovernanceCredentialAlertsApi:
    def test_get_returns_sorted_expiry_alerts(self, app):
        api = ExternalAppGovernanceCredentialAlertsApi()
        method = unwrap(api.get)
        now_ts = int(datetime.now(tz=UTC).timestamp())

        app_expired = SimpleNamespace(
            id="app-expired",
            tenant_id="tenant-1",
            name="Expired App",
            auth_mode=SimpleNamespace(value="oauth2_authorization_code"),
            auth_config={"expires_at": now_ts - 30},
            created_at=None,
        )
        app_warning = SimpleNamespace(
            id="app-warning",
            tenant_id="tenant-1",
            name="Warning App",
            auth_mode=SimpleNamespace(value="oauth2_authorization_code"),
            auth_config={"expires_at": now_ts + 3600},
            created_at=None,
        )
        app_no_alert = SimpleNamespace(
            id="app-ok",
            tenant_id="tenant-1",
            name="Ok App",
            auth_mode=SimpleNamespace(value="oauth2_authorization_code"),
            auth_config={"expires_at": now_ts + 10 * 24 * 3600},
            created_at=None,
        )

        fake_session = MagicMock()
        fake_session.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[app_expired, app_warning, app_no_alert])
        )

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/governance/credential-alerts?within_hours=72",
                method="GET",
            ),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_management.db.session", fake_session),
        ):
            result, status = method(api)

        assert status == 200
        assert result["summary"]["within_hours"] == 72
        assert result["summary"]["total_alerts"] == 2
        assert [item["app_id"] for item in result["alerts"]] == ["app-expired", "app-warning"]
        assert result["alerts"][0]["alert_level"] == "expired"

    def test_get_rejects_invalid_within_hours(self, app):
        api = ExternalAppGovernanceCredentialAlertsApi()
        method = unwrap(api.get)

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/governance/credential-alerts?within_hours=0",
                method="GET",
            ),
            patch(
                "controllers.console.workspace.external_app_management._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 400
