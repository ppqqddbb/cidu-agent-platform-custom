"""Inner API endpoints for external tenant and RBAC synchronization."""

from __future__ import annotations

from datetime import datetime

from flask_restx import Resource
from pydantic import BaseModel, ConfigDict, Field

from controllers.common.schema import register_enum_models, register_schema_models
from controllers.console.wraps import setup_required
from controllers.inner_api import inner_api_ns
from controllers.inner_api.wraps import enterprise_inner_api_only
from models import AccountStatus, ExternalManagementMode, TenantAccountRole, TenantStatus
from services.errors.integration import (
    ExternalBindingNotFoundError,
    ExternalIntegrityError,
    IntegrationVersionConflictError,
    UnsupportedIntegrationEventError,
)
from services.external_identity_service import ExternalIdentityService


class IntegrationPayloadBase(BaseModel):
    source_version: int = Field(ge=0)
    event_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class TenantUpsertPayload(IntegrationPayloadBase):
    name: str = Field(min_length=1, max_length=255)
    status: TenantStatus = TenantStatus.NORMAL
    management_mode: ExternalManagementMode = ExternalManagementMode.LOCAL_MANAGED
    allow_local_member_override: bool = False


class UserUpsertPayload(IntegrationPayloadBase):
    email: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    avatar: str | None = Field(default=None, max_length=255)
    status: AccountStatus = AccountStatus.ACTIVE


class MembershipUpsertPayload(IntegrationPayloadBase):
    display_role: TenantAccountRole = TenantAccountRole.NORMAL


class MembershipDeletePayload(IntegrationPayloadBase):
    pass


class AuthorizationReplacePayload(IntegrationPayloadBase):
    capabilities: list[str] = Field(default_factory=list)
    expires_at: datetime


class AuthorizationResolvePayload(BaseModel):
    external_tenant_id: str = Field(min_length=1, max_length=255)
    external_user_id: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(extra="forbid")


class EventTenantPayload(TenantUpsertPayload):
    external_tenant_id: str = Field(min_length=1, max_length=255)


class EventUserPayload(UserUpsertPayload):
    external_user_id: str = Field(min_length=1, max_length=255)


class EventMembershipUpsertPayload(MembershipUpsertPayload):
    external_tenant_id: str = Field(min_length=1, max_length=255)
    external_user_id: str = Field(min_length=1, max_length=255)


class EventMembershipDeletePayload(MembershipDeletePayload):
    external_tenant_id: str = Field(min_length=1, max_length=255)
    external_user_id: str = Field(min_length=1, max_length=255)


class EventAuthorizationReplacePayload(AuthorizationReplacePayload):
    external_tenant_id: str = Field(min_length=1, max_length=255)
    external_user_id: str = Field(min_length=1, max_length=255)


class IntegrationEventPayload(BaseModel):
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=255)
    source_version: int = Field(ge=0)
    occurred_at: datetime | None = None
    payload: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


register_schema_models(
    inner_api_ns,
    TenantUpsertPayload,
    UserUpsertPayload,
    MembershipUpsertPayload,
    MembershipDeletePayload,
    AuthorizationReplacePayload,
    AuthorizationResolvePayload,
    EventTenantPayload,
    EventUserPayload,
    EventMembershipUpsertPayload,
    EventMembershipDeletePayload,
    EventAuthorizationReplacePayload,
    IntegrationEventPayload,
)
register_enum_models(inner_api_ns, TenantStatus, AccountStatus, ExternalManagementMode, TenantAccountRole)


def _handle_integration_error(exc: Exception) -> tuple[dict[str, str], int]:
    if isinstance(exc, ExternalBindingNotFoundError):
        return {"message": exc.description or str(exc)}, 404
    if isinstance(exc, UnsupportedIntegrationEventError):
        return {"message": exc.description or str(exc)}, 400
    if isinstance(exc, (ExternalIntegrityError, IntegrationVersionConflictError)):
        return {"message": exc.description or str(exc)}, 409
    raise exc


def _dispatch_integration_event(args: IntegrationEventPayload):
    payload = args.payload

    if args.event_type == "tenant.upsert":
        event_payload = EventTenantPayload.model_validate(
            {**payload, "event_id": args.event_id, "source_version": args.source_version}
        )
        return ExternalIdentityService.upsert_tenant(
            external_tenant_id=event_payload.external_tenant_id,
            name=event_payload.name,
            status=event_payload.status,
            management_mode=event_payload.management_mode,
            allow_local_member_override=event_payload.allow_local_member_override,
            source_version=event_payload.source_version,
            event_id=args.event_id,
            event_type=args.event_type,
            event_payload=args.model_dump(mode="json"),
        )

    if args.event_type == "user.upsert":
        event_payload = EventUserPayload.model_validate(
            {**payload, "event_id": args.event_id, "source_version": args.source_version}
        )
        return ExternalIdentityService.upsert_user(
            external_user_id=event_payload.external_user_id,
            email=event_payload.email,
            name=event_payload.name,
            avatar=event_payload.avatar,
            status=event_payload.status,
            source_version=event_payload.source_version,
            event_id=args.event_id,
            event_type=args.event_type,
            event_payload=args.model_dump(mode="json"),
        )

    if args.event_type == "membership.upsert":
        event_payload = EventMembershipUpsertPayload.model_validate(
            {**payload, "event_id": args.event_id, "source_version": args.source_version}
        )
        return ExternalIdentityService.upsert_membership(
            external_tenant_id=event_payload.external_tenant_id,
            external_user_id=event_payload.external_user_id,
            display_role=event_payload.display_role,
            source_version=event_payload.source_version,
            event_id=args.event_id,
            event_type=args.event_type,
            event_payload=args.model_dump(mode="json"),
        )

    if args.event_type == "membership.delete":
        event_payload = EventMembershipDeletePayload.model_validate(
            {**payload, "event_id": args.event_id, "source_version": args.source_version}
        )
        return ExternalIdentityService.remove_membership(
            external_tenant_id=event_payload.external_tenant_id,
            external_user_id=event_payload.external_user_id,
            source_version=event_payload.source_version,
            event_id=args.event_id,
            event_type=args.event_type,
            event_payload=args.model_dump(mode="json"),
        )

    if args.event_type == "authorization.replace":
        event_payload = EventAuthorizationReplacePayload.model_validate(
            {**payload, "event_id": args.event_id, "source_version": args.source_version}
        )
        return ExternalIdentityService.replace_authorization(
            external_tenant_id=event_payload.external_tenant_id,
            external_user_id=event_payload.external_user_id,
            capabilities=event_payload.capabilities,
            expires_at=event_payload.expires_at,
            source_version=event_payload.source_version,
            event_id=args.event_id,
            event_type=args.event_type,
            event_payload=args.model_dump(mode="json"),
        )

    raise UnsupportedIntegrationEventError(f"unsupported event_type: {args.event_type}")


@inner_api_ns.route("/integration/tenants/<string:external_tenant_id>")
class IntegrationTenantApi(Resource):
    method_decorators = [setup_required, enterprise_inner_api_only]

    @inner_api_ns.expect(inner_api_ns.models[TenantUpsertPayload.__name__])
    def put(self, external_tenant_id: str):
        args = TenantUpsertPayload.model_validate(inner_api_ns.payload or {})
        try:
            result = ExternalIdentityService.upsert_tenant(
                external_tenant_id=external_tenant_id,
                name=args.name,
                status=args.status,
                management_mode=args.management_mode,
                allow_local_member_override=args.allow_local_member_override,
                source_version=args.source_version,
                event_id=args.event_id,
                event_payload=args.model_dump(mode="json"),
            )
        except Exception as exc:
            return _handle_integration_error(exc)
        return result.to_dict(), 200


@inner_api_ns.route("/integration/users/<string:external_user_id>")
class IntegrationUserApi(Resource):
    method_decorators = [setup_required, enterprise_inner_api_only]

    @inner_api_ns.expect(inner_api_ns.models[UserUpsertPayload.__name__])
    def put(self, external_user_id: str):
        args = UserUpsertPayload.model_validate(inner_api_ns.payload or {})
        try:
            result = ExternalIdentityService.upsert_user(
                external_user_id=external_user_id,
                email=args.email,
                name=args.name,
                avatar=args.avatar,
                status=args.status,
                source_version=args.source_version,
                event_id=args.event_id,
                event_payload=args.model_dump(mode="json"),
            )
        except Exception as exc:
            return _handle_integration_error(exc)
        return result.to_dict(), 200


@inner_api_ns.route("/integration/tenants/<string:external_tenant_id>/members/<string:external_user_id>")
class IntegrationMembershipApi(Resource):
    method_decorators = [setup_required, enterprise_inner_api_only]

    @inner_api_ns.expect(inner_api_ns.models[MembershipUpsertPayload.__name__])
    def put(self, external_tenant_id: str, external_user_id: str):
        args = MembershipUpsertPayload.model_validate(inner_api_ns.payload or {})
        try:
            result = ExternalIdentityService.upsert_membership(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                display_role=args.display_role,
                source_version=args.source_version,
                event_id=args.event_id,
                event_payload=args.model_dump(mode="json"),
            )
        except Exception as exc:
            return _handle_integration_error(exc)
        return result.to_dict(), 200

    @inner_api_ns.expect(inner_api_ns.models[MembershipDeletePayload.__name__])
    def delete(self, external_tenant_id: str, external_user_id: str):
        args = MembershipDeletePayload.model_validate(inner_api_ns.payload or {})
        try:
            result = ExternalIdentityService.remove_membership(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                source_version=args.source_version,
                event_id=args.event_id,
                event_payload=args.model_dump(mode="json"),
            )
        except Exception as exc:
            return _handle_integration_error(exc)
        return result.to_dict(), 200


@inner_api_ns.route("/integration/tenants/<string:external_tenant_id>/members/<string:external_user_id>/authorization")
class IntegrationAuthorizationApi(Resource):
    method_decorators = [setup_required, enterprise_inner_api_only]

    @inner_api_ns.expect(inner_api_ns.models[AuthorizationReplacePayload.__name__])
    def put(self, external_tenant_id: str, external_user_id: str):
        args = AuthorizationReplacePayload.model_validate(inner_api_ns.payload or {})
        try:
            result = ExternalIdentityService.replace_authorization(
                external_tenant_id=external_tenant_id,
                external_user_id=external_user_id,
                capabilities=args.capabilities,
                expires_at=args.expires_at,
                source_version=args.source_version,
                event_id=args.event_id,
                event_payload=args.model_dump(mode="json"),
            )
        except Exception as exc:
            return _handle_integration_error(exc)
        return result.to_dict(), 200


@inner_api_ns.route("/integration/authorization/resolve")
class IntegrationAuthorizationResolveApi(Resource):
    method_decorators = [setup_required, enterprise_inner_api_only]

    @inner_api_ns.expect(inner_api_ns.models[AuthorizationResolvePayload.__name__])
    def post(self):
        args = AuthorizationResolvePayload.model_validate(inner_api_ns.payload or {})
        try:
            result = ExternalIdentityService.resolve_authorization(
                external_tenant_id=args.external_tenant_id,
                external_user_id=args.external_user_id,
            )
        except Exception as exc:
            return _handle_integration_error(exc)
        return result.to_dict(), 200


@inner_api_ns.route("/integration/events")
class IntegrationEventApi(Resource):
    method_decorators = [setup_required, enterprise_inner_api_only]

    @inner_api_ns.expect(inner_api_ns.models[IntegrationEventPayload.__name__])
    def post(self):
        args = IntegrationEventPayload.model_validate(inner_api_ns.payload or {})

        try:
            result = _dispatch_integration_event(args)
        except Exception as exc:
            return _handle_integration_error(exc)

        response = result.to_dict()
        response["event_type"] = args.event_type
        return response, 200
