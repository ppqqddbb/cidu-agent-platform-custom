"""
Unit tests for inner_api integration module.

These tests focus on payload validation and endpoint handler orchestration.
Decorator behavior is covered separately in inner_api auth wrapper tests.
"""

import inspect
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from pydantic import ValidationError

from controllers.inner_api.integration import (
    AuthorizationResolvePayload,
    IntegrationAuthorizationResolveApi,
    IntegrationEventApi,
    IntegrationEventPayload,
    IntegrationTenantApi,
    TenantUpsertPayload,
)
from models import ExternalManagementMode, TenantAccountRole, TenantStatus
from services.errors.integration import IntegrationVersionConflictError
from services.external_identity_service import IntegrationMutationResult, IntegrationResolveResult


def call_unwrapped(method, *args):
    # `inspect.unwrap()` 返回的这里仍然是绑定到实例的方法；
    # 调用时如果再次手动传入 `self`，会把参数数量撑错。
    return inspect.unwrap(method)(*args)


class TestTenantUpsertPayload:
    def test_valid_payload(self) -> None:
        payload = TenantUpsertPayload.model_validate(
            {
                "name": "External Workspace",
                "status": "normal",
                "management_mode": "external_managed",
                "allow_local_member_override": True,
                "source_version": 3,
            }
        )
        assert payload.name == "External Workspace"
        assert payload.status == TenantStatus.NORMAL
        assert payload.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
        assert payload.allow_local_member_override is True

    def test_missing_name_fails(self) -> None:
        with pytest.raises(ValidationError):
            TenantUpsertPayload.model_validate({"source_version": 1})


class TestAuthorizationResolvePayload:
    def test_valid_payload(self) -> None:
        payload = AuthorizationResolvePayload.model_validate(
            {"external_tenant_id": "tenant-ext", "external_user_id": "user-ext"}
        )
        assert payload.external_tenant_id == "tenant-ext"
        assert payload.external_user_id == "user-ext"

    def test_missing_fields_fail(self) -> None:
        with pytest.raises(ValidationError):
            AuthorizationResolvePayload.model_validate({"external_tenant_id": "tenant-ext"})


class TestIntegrationEventPayload:
    def test_valid_event_payload(self) -> None:
        payload = IntegrationEventPayload.model_validate(
            {
                "event_id": "evt-1",
                "event_type": "tenant.upsert",
                "source_version": 4,
                "payload": {"external_tenant_id": "tenant-ext", "name": "Workspace"},
            }
        )
        assert payload.event_id == "evt-1"
        assert payload.event_type == "tenant.upsert"


class TestIntegrationTenantApi:
    @pytest.fixture
    def api_instance(self) -> IntegrationTenantApi:
        return IntegrationTenantApi()

    @patch("controllers.inner_api.integration.ExternalIdentityService")
    def test_put_calls_service(self, mock_service: MagicMock, api_instance: IntegrationTenantApi, app: Flask) -> None:
        mock_service.upsert_tenant.return_value = IntegrationMutationResult(
            applied=True,
            tenant_id="tenant-1",
            external_tenant_id="tenant-ext",
        )

        with app.test_request_context():
            with patch("controllers.inner_api.integration.inner_api_ns") as mock_ns:
                mock_ns.payload = {
                    "name": "External Workspace",
                    "status": "normal",
                    "management_mode": "external_managed",
                    "allow_local_member_override": True,
                    "source_version": 8,
                }
                result = call_unwrapped(api_instance.put, "tenant-ext")

        assert result[1] == 200
        assert result[0]["applied"] is True
        mock_service.upsert_tenant.assert_called_once()

    @patch("controllers.inner_api.integration.ExternalIdentityService")
    def test_put_maps_version_conflict(
        self,
        mock_service: MagicMock,
        api_instance: IntegrationTenantApi,
        app: Flask,
    ) -> None:
        mock_service.upsert_tenant.side_effect = IntegrationVersionConflictError("version conflict")

        with app.test_request_context():
            with patch("controllers.inner_api.integration.inner_api_ns") as mock_ns:
                mock_ns.payload = {
                    "name": "External Workspace",
                    "source_version": 8,
                }
                result = call_unwrapped(api_instance.put, "tenant-ext")

        assert result == ({"message": "version conflict"}, 409)


class TestIntegrationAuthorizationResolveApi:
    @pytest.fixture
    def api_instance(self) -> IntegrationAuthorizationResolveApi:
        return IntegrationAuthorizationResolveApi()

    @patch("controllers.inner_api.integration.ExternalIdentityService")
    def test_post_returns_resolved_snapshot(
        self,
        mock_service: MagicMock,
        api_instance: IntegrationAuthorizationResolveApi,
        app: Flask,
    ) -> None:
        mock_service.resolve_authorization.return_value = IntegrationResolveResult(
            tenant_id="tenant-1",
            account_id="account-1",
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            management_mode=ExternalManagementMode.EXTERNAL_MANAGED,
            allow_local_member_override=False,
            membership_active=True,
            display_role=TenantAccountRole.ADMIN,
            capabilities=["workspace.view"],
            projection_source_version=9,
            projection_expires_at=datetime(2026, 4, 9, 12, 0, 0),
        )

        with app.test_request_context():
            with patch("controllers.inner_api.integration.inner_api_ns") as mock_ns:
                mock_ns.payload = {"external_tenant_id": "tenant-ext", "external_user_id": "user-ext"}
                result = call_unwrapped(api_instance.post)

        assert result[1] == 200
        assert result[0]["management_mode"] == "external_managed"
        assert result[0]["capabilities"] == ["workspace.view"]


class TestIntegrationEventApi:
    @pytest.fixture
    def api_instance(self) -> IntegrationEventApi:
        return IntegrationEventApi()

    @patch("controllers.inner_api.integration.ExternalIdentityService")
    def test_post_dispatches_membership_delete(
        self,
        mock_service: MagicMock,
        api_instance: IntegrationEventApi,
        app: Flask,
    ) -> None:
        mock_service.remove_membership.return_value = IntegrationMutationResult(
            applied=True,
            tenant_id="tenant-1",
            account_id="account-1",
            external_tenant_id="tenant-ext",
            external_user_id="user-ext",
            event_id="evt-1",
        )

        with app.test_request_context():
            with patch("controllers.inner_api.integration.inner_api_ns") as mock_ns:
                mock_ns.payload = {
                    "event_id": "evt-1",
                    "event_type": "membership.delete",
                    "source_version": 10,
                    "payload": {
                        "external_tenant_id": "tenant-ext",
                        "external_user_id": "user-ext",
                    },
                }
                result = call_unwrapped(api_instance.post)

        assert result[1] == 200
        assert result[0]["event_type"] == "membership.delete"
        mock_service.remove_membership.assert_called_once()

    def test_post_rejects_unsupported_event_type(self, api_instance: IntegrationEventApi, app: Flask) -> None:
        with app.test_request_context():
            with patch("controllers.inner_api.integration.inner_api_ns") as mock_ns:
                mock_ns.payload = {
                    "event_id": "evt-2",
                    "event_type": "membership.sync",
                    "source_version": 11,
                    "payload": {},
                }
                result = call_unwrapped(api_instance.post)

        assert result == ({"message": "unsupported event_type: membership.sync"}, 400)
