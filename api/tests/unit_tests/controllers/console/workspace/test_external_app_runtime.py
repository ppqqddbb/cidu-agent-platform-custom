from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controllers.console.workspace.external_app_runtime import (
    RUNTIME_PERMISSION_TENANT_SCOPED,
    RUNTIME_PERMISSION_UNVERIFIED,
    ExternalAppRuntimeAuditRecordsApi,
    ExternalAppRuntimeAuditSummaryApi,
    ExternalAppRuntimeAvailableApisApi,
    ExternalAppRuntimeInvokeApi,
    _build_invoke_credential_auth,
    _extract_failure_reason,
    _resolve_permission,
)
from core.tools.errors import ToolInvokeError
from libs.datetime_utils import naive_utc_now


def unwrap(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


def build_log(
    *,
    log_id: str,
    content: dict[str, object],
    account_id: str = "account-1",
    tenant_id: str = "tenant-1",
):
    return SimpleNamespace(
        id=log_id,
        tenant_id=tenant_id,
        account_id=account_id,
        action="external_app_runtime.invoke",
        content=content,
        created_ip="127.0.0.1",
        created_at=naive_utc_now(),
    )


class TestExternalAppRuntimeAvailableApisApi:
    def test_post_proxies_runtime_common_response(self, app):
        api = ExternalAppRuntimeAvailableApisApi()
        method = unwrap(api.post)

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/available-apis",
                method="POST",
                json={"query": "order", "context_token": "token-1", "max_results": 20},
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_runtime.runtime_common.list_available_apis",
                return_value={
                    "apis": [{"app_id": "app-1", "api_id": "api-1", "allowed": True}],
                    "summary": {"total": 1, "routing_strategy": "app_first_v1"},
                },
            ) as mock_list,
        ):
            result, status = method(api)

        assert status == 200
        assert result["summary"]["routing_strategy"] == "app_first_v1"
        assert result["apis"][0]["app_id"] == "app-1"
        assert mock_list.call_args.kwargs["tenant_id"] == "tenant-1"
        assert mock_list.call_args.kwargs["only_allowed"] is False

    def test_post_maps_context_token_error_to_401(self, app):
        api = ExternalAppRuntimeAvailableApisApi()
        method = unwrap(api.post)

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/available-apis",
                method="POST",
                json={"query": "order", "context_token": "expired-token"},
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_runtime.runtime_common.list_available_apis",
                side_effect=ToolInvokeError("context_token has expired."),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 401


class TestExternalAppRuntimeInvokeApi:
    def test_post_calls_runtime_common_invoke_api(self, app):
        api = ExternalAppRuntimeInvokeApi()
        method = unwrap(api.post)
        current_user = MagicMock(id="account-1")

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/invoke",
                method="POST",
                json={
                    "app_id": "app-1",
                    "api_id": "api-1",
                    "dry_run": True,
                    "params": {"query": {"order_no": "A001"}},
                },
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(current_user, "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_runtime.runtime_common.invoke_api",
                return_value={"result": "success", "dry_run": True, "trace_id": "trace-1"},
            ) as mock_invoke,
        ):
            result, status = method(api)

        assert status == 200
        assert result["result"] == "success"
        assert result["dry_run"] is True
        assert mock_invoke.call_args.kwargs["account_id"] == "account-1"
        assert mock_invoke.call_args.kwargs["invoke_from"] == "console_runtime"

    def test_post_maps_permission_error_to_403(self, app):
        api = ExternalAppRuntimeInvokeApi()
        method = unwrap(api.post)

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/invoke",
                method="POST",
                json={"app_id": "app-1", "api_id": "api-1", "dry_run": True, "params": {}},
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch(
                "controllers.console.workspace.external_app_runtime.runtime_common.invoke_api",
                side_effect=ToolInvokeError("Current auth context does not satisfy required_permissions."),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 403


class TestExternalAppRuntimePermissionAndCredentialAdapters:
    def test_resolve_permission_returns_tenant_scoped_when_token_not_verified(self):
        allowed, permission_level, warnings = _resolve_permission(
            required_permissions=["order.read"],
            context_capabilities=[],
            token_verified=False,
        )

        assert allowed is True
        assert permission_level == RUNTIME_PERMISSION_TENANT_SCOPED
        assert "tenant_scoped_fallback_without_verified_token" in warnings

    def test_resolve_permission_returns_unverified_in_direct_mode_without_context(self):
        allowed, permission_level, warnings = _resolve_permission(
            required_permissions=["order.read"],
            context_capabilities=[],
            token_verified=False,
            call_mode="direct",
        )

        assert allowed is True
        assert permission_level == RUNTIME_PERMISSION_UNVERIFIED
        assert "direct_mode_unverified_authorization_context" in warnings

    def test_build_invoke_credential_auth_static_bearer(self):
        app_item = SimpleNamespace(
            id="app-1",
            auth_mode=SimpleNamespace(value="static_bearer"),
            auth_config={"token": "token-1"},
        )

        headers, query_params, warnings = _build_invoke_credential_auth(app=app_item, timeout_seconds=15.0)

        assert headers["Authorization"] == "Bearer token-1"
        assert query_params == {}
        assert warnings == []

    def test_build_invoke_credential_auth_static_bearer_strips_prefix(self):
        app_item = SimpleNamespace(
            id="app-1",
            auth_mode=SimpleNamespace(value="static_bearer"),
            auth_config={"token": "Bearer token-1"},
        )

        headers, query_params, warnings = _build_invoke_credential_auth(app=app_item, timeout_seconds=15.0)

        assert headers["Authorization"] == "Bearer token-1"
        assert query_params == {}
        assert warnings == []

    def test_build_invoke_credential_auth_custom_api_key_query(self):
        app_item = SimpleNamespace(
            id="app-1",
            auth_mode=SimpleNamespace(value="custom"),
            auth_config={
                "type": "api_key",
                "api_key": "api-key-value",
                "api_key_in": "query",
                "api_key_name": "apikey",
            },
        )

        headers, query_params, warnings = _build_invoke_credential_auth(app=app_item, timeout_seconds=15.0)

        assert headers == {}
        assert query_params["apikey"] == "api-key-value"
        assert warnings == []


class TestExternalAppRuntimeAuditSummaryApi:
    def test_extract_failure_reason_supports_business_failed_payload(self):
        reason = _extract_failure_reason(
            {
                "business_failed": True,
                "business_message": "内部服务器错误",
                "response_status": 200,
                "warnings": [],
            }
        )

        assert reason == "business_error:内部服务器错误"

    def test_get_returns_aggregated_summary(self, app):
        api = ExternalAppRuntimeAuditSummaryApi()
        method = unwrap(api.get)
        logs = [
            build_log(
                log_id="log-1",
                content={
                    "trace_id": "t-1",
                    "app_id": "app-1",
                    "api_id": "api-1",
                    "dry_run": True,
                    "invoke_from": "builtin_tool",
                    "warnings": [],
                },
            ),
            build_log(
                log_id="log-2",
                content={
                    "trace_id": "t-2",
                    "app_id": "app-1",
                    "api_id": "api-1",
                    "dry_run": False,
                    "invoke_from": "builtin_tool",
                    "warnings": ["request_error:TimeoutError"],
                },
            ),
            build_log(
                log_id="log-3",
                content={
                    "trace_id": "t-3",
                    "app_id": "app-2",
                    "api_id": "api-9",
                    "dry_run": False,
                    "invoke_from": "console_runtime",
                    "response_status": 503,
                    "warnings": [],
                },
            ),
        ]
        fake_session = MagicMock()
        fake_session.scalars.return_value = MagicMock(all=MagicMock(return_value=logs))

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/audit/summary?window_hours=24&top_n=5",
                method="GET",
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_runtime.db.session", fake_session),
        ):
            result, status = method(api)

        assert status == 200
        assert result["summary"]["total_calls"] == 3
        assert result["summary"]["failed_calls"] == 2
        assert result["summary"]["success_calls"] == 1
        assert result["summary"]["dry_run_calls"] == 1
        assert result["summary"]["source_breakdown"]["builtin_tool"] == 2
        reasons = {item["reason"] for item in result["failure_reasons"]}
        assert "request_error:TimeoutError" in reasons
        assert "response_status:503" in reasons
        assert result["api_health"][0]["app_id"] == "app-2"


class TestExternalAppRuntimeAuditRecordsApi:
    def test_get_filters_failure_and_paginates(self, app):
        api = ExternalAppRuntimeAuditRecordsApi()
        method = unwrap(api.get)
        logs = [
            build_log(
                log_id="log-failure",
                content={
                    "trace_id": "t-f",
                    "app_id": "app-1",
                    "api_id": "api-1",
                    "dry_run": False,
                    "invoke_from": "console_runtime",
                    "warnings": ["request_error:ConnectionError"],
                },
            ),
            build_log(
                log_id="log-success",
                content={
                    "trace_id": "t-s",
                    "app_id": "app-1",
                    "api_id": "api-2",
                    "dry_run": False,
                    "invoke_from": "console_runtime",
                    "warnings": [],
                    "response_status": 200,
                },
            ),
            build_log(
                log_id="log-dry-run",
                content={
                    "trace_id": "t-d",
                    "app_id": "app-1",
                    "api_id": "api-3",
                    "dry_run": True,
                    "invoke_from": "builtin_tool",
                    "warnings": [],
                },
            ),
        ]
        fake_session = MagicMock()
        fake_session.scalars.return_value = MagicMock(all=MagicMock(return_value=logs))

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/audit/records?outcome=failure&include_dry_run=false&page=1&page_size=1",
                method="GET",
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
            patch("controllers.console.workspace.external_app_runtime.db.session", fake_session),
        ):
            result, status = method(api)

        assert status == 200
        assert result["pagination"]["total"] == 1
        assert len(result["records"]) == 1
        assert result["records"][0]["id"] == "log-failure"
        assert result["records"][0]["failed"] is True

    def test_get_rejects_invalid_outcome(self, app):
        api = ExternalAppRuntimeAuditRecordsApi()
        method = unwrap(api.get)

        with (
            app.test_request_context(
                "/workspaces/current/external-apps/runtime/audit/records?outcome=bad",
                method="GET",
            ),
            patch(
                "controllers.console.workspace.external_app_runtime._ensure_account_and_tenant",
                return_value=(MagicMock(id="account-1"), "tenant-1"),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                method(api)

        assert exc_info.value.code == 400
