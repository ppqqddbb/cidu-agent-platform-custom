from __future__ import annotations

from flask import abort
from flask_restx import Resource
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    capability_required,
    setup_required,
)
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from libs.login import current_account_with_tenant, login_required
from models import ExternalAccountBinding, ExternalManagementMode, ExternalTenantBinding
from models.account import Account, Tenant, TenantAccountJoin
from services.account_service import TenantService
from services.errors.integration import ExternalBindingNotFoundError
from services.external_identity_service import ExternalIdentityService

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"


class TenantManagementUpdatePayload(BaseModel):
    management_mode: ExternalManagementMode
    allow_local_member_override: bool = False
    external_tenant_id: str | None = Field(default=None, min_length=1, max_length=255)


class TenantCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    management_mode: ExternalManagementMode = ExternalManagementMode.LOCAL_MANAGED
    allow_local_member_override: bool = False
    external_tenant_id: str | None = Field(default=None, min_length=1, max_length=255)


def reg(cls: type[BaseModel]):
    console_ns.schema_model(cls.__name__, cls.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0))


reg(TenantManagementUpdatePayload)
reg(TenantCreatePayload)


def _serialize_binding(binding: ExternalTenantBinding | None) -> dict[str, object] | None:
    if binding is None:
        return None
    return {
        "external_tenant_id": binding.external_tenant_id,
        "source_version": binding.source_version,
        "last_synced_at": int(binding.last_synced_at.timestamp()) if binding.last_synced_at else None,
    }


def _build_tenant_management_response(*, tenant_id: str) -> dict[str, object]:
    binding = db.session.scalar(
        select(ExternalTenantBinding).where(ExternalTenantBinding.tenant_id == tenant_id).limit(1)
    )
    if binding is None:
        return {
            "tenant_id": tenant_id,
            "management_mode": ExternalManagementMode.LOCAL_MANAGED.value,
            "allow_local_member_override": False,
            "has_external_binding": False,
            "external_tenant_binding": None,
        }

    return {
        "tenant_id": tenant_id,
        "management_mode": binding.management_mode.value,
        "allow_local_member_override": binding.allow_local_member_override,
        "has_external_binding": True,
        "external_tenant_binding": _serialize_binding(binding),
    }


def _ensure_super_admin() -> tuple[Account, str | None]:
    current_user, current_tenant_id = current_account_with_tenant()
    if not isinstance(current_user, Account):
        abort(401, "Unauthorized.")
    if not TenantService.is_super_admin(current_user):
        abort(403, "Super admin permission required.")
    return current_user, current_tenant_id


def _serialize_tenant_for_admin(
    tenant: Tenant,
    *,
    default_tenant_id: str | None,
    binding: ExternalTenantBinding | None,
    member_count: int,
) -> dict[str, object]:
    management_mode = ExternalManagementMode.LOCAL_MANAGED.value
    allow_local_member_override = False
    external_tenant_id: str | None = None
    if binding is not None:
        management_mode = binding.management_mode.value
        allow_local_member_override = binding.allow_local_member_override
        external_tenant_id = binding.external_tenant_id

    return {
        "id": tenant.id,
        "name": tenant.name,
        "status": tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status),
        "created_at": int(tenant.created_at.timestamp()) if tenant.created_at else None,
        "is_default_tenant": tenant.id == default_tenant_id,
        "member_count": member_count,
        "management_mode": management_mode,
        "allow_local_member_override": allow_local_member_override,
        "external_tenant_id": external_tenant_id,
    }


@console_ns.route("/workspaces/current/tenant-management")
class TenantManagementApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self):
        _, current_tenant_id = _ensure_super_admin()
        if not current_tenant_id:
            raise ValueError("No current tenant")
        return _build_tenant_management_response(tenant_id=current_tenant_id), 200

    @console_ns.expect(console_ns.models[TenantManagementUpdatePayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def post(self):
        _, current_tenant_id = _ensure_super_admin()
        if not current_tenant_id:
            raise ValueError("No current tenant")

        payload = console_ns.payload or {}
        args = TenantManagementUpdatePayload.model_validate(payload)
        default_tenant = TenantService.get_default_tenant()
        if (
            default_tenant is not None
            and current_tenant_id == default_tenant.id
            and args.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
        ):
            abort(400, "Default workspace cannot be configured as external managed.")
        desired_external_tenant_id = args.external_tenant_id.strip() if args.external_tenant_id else None
        desired_allow_local_override = (
            args.allow_local_member_override
            if args.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
            else False
        )

        binding = db.session.scalar(
            select(ExternalTenantBinding).where(ExternalTenantBinding.tenant_id == current_tenant_id).limit(1)
        )

        if (
            binding is None
            and args.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
            and not desired_external_tenant_id
        ):
            abort(400, "external_tenant_id is required when enabling external management.")

        if desired_external_tenant_id:
            conflict_binding = db.session.scalar(
                select(ExternalTenantBinding)
                .where(ExternalTenantBinding.external_tenant_id == desired_external_tenant_id)
                .limit(1)
            )
            if conflict_binding is not None and conflict_binding.tenant_id != current_tenant_id:
                abort(409, "external_tenant_id is already bound to another workspace.")

        if binding is None:
            if args.management_mode == ExternalManagementMode.LOCAL_MANAGED:
                return {
                    "result": "success",
                    "tenant_management": _build_tenant_management_response(tenant_id=current_tenant_id),
                }, 200

            assert desired_external_tenant_id is not None
            binding = ExternalTenantBinding(
                external_tenant_id=desired_external_tenant_id,
                tenant_id=current_tenant_id,
                source_version=0,
                management_mode=args.management_mode,
                allow_local_member_override=desired_allow_local_override,
                last_synced_at=naive_utc_now(),
            )
            db.session.add(binding)
        else:
            if desired_external_tenant_id:
                binding.external_tenant_id = desired_external_tenant_id
            binding.management_mode = args.management_mode
            binding.allow_local_member_override = desired_allow_local_override
            binding.last_synced_at = naive_utc_now()

        db.session.commit()
        return {
            "result": "success",
            "tenant_management": _build_tenant_management_response(tenant_id=current_tenant_id),
        }, 200


@console_ns.route("/workspaces/current/tenant-management/sync")
class TenantManagementSyncApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def post(self):
        current_user, current_tenant_id = _ensure_super_admin()
        if not current_tenant_id:
            raise ValueError("No current tenant")

        tenant_binding = db.session.scalar(
            select(ExternalTenantBinding).where(ExternalTenantBinding.tenant_id == current_tenant_id).limit(1)
        )
        if tenant_binding is None:
            abort(400, "Current workspace is not bound to an external tenant.")

        account_binding = db.session.scalar(
            select(ExternalAccountBinding).where(ExternalAccountBinding.account_id == current_user.id).limit(1)
        )
        if account_binding is None:
            abort(400, "Current account is not bound to an external user.")

        try:
            result = ExternalIdentityService.resolve_authorization(
                external_tenant_id=tenant_binding.external_tenant_id,
                external_user_id=account_binding.external_user_id,
            )
        except ExternalBindingNotFoundError as exc:
            abort(400, str(exc))

        return {"result": "success", "resolve": result.to_dict()}, 200


@console_ns.route("/workspaces/tenant-management/tenants")
class TenantManagementTenantsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        _ensure_super_admin()

        tenants = list(db.session.scalars(select(Tenant).order_by(Tenant.created_at.asc(), Tenant.id.asc())).all())
        if not tenants:
            return {"tenants": []}, 200

        tenant_ids = [tenant.id for tenant in tenants]

        bindings = list(
            db.session.scalars(
                select(ExternalTenantBinding).where(ExternalTenantBinding.tenant_id.in_(tenant_ids))
            ).all()
        )
        binding_by_tenant_id = {binding.tenant_id: binding for binding in bindings}

        member_count_rows = db.session.execute(
            select(TenantAccountJoin.tenant_id, func.count(TenantAccountJoin.id))
            .where(TenantAccountJoin.tenant_id.in_(tenant_ids))
            .group_by(TenantAccountJoin.tenant_id)
        )
        member_count_by_tenant_id = {tenant_id: int(member_count) for tenant_id, member_count in member_count_rows}

        default_tenant = TenantService.get_default_tenant()
        default_tenant_id = default_tenant.id if default_tenant else None

        return {
            "tenants": [
                _serialize_tenant_for_admin(
                    tenant,
                    default_tenant_id=default_tenant_id,
                    binding=binding_by_tenant_id.get(tenant.id),
                    member_count=member_count_by_tenant_id.get(tenant.id, 0),
                )
                for tenant in tenants
            ]
        }, 200

    @console_ns.expect(console_ns.models[TenantCreatePayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        _ensure_super_admin()
        payload = console_ns.payload or {}
        args = TenantCreatePayload.model_validate(payload)

        tenant_name = args.name.strip()
        desired_external_tenant_id = args.external_tenant_id.strip() if args.external_tenant_id else None
        desired_allow_override = (
            args.allow_local_member_override
            if args.management_mode == ExternalManagementMode.EXTERNAL_MANAGED
            else False
        )

        if args.management_mode == ExternalManagementMode.EXTERNAL_MANAGED and not desired_external_tenant_id:
            abort(400, "external_tenant_id is required when enabling external management.")

        if desired_external_tenant_id:
            conflict_binding = db.session.scalar(
                select(ExternalTenantBinding)
                .where(ExternalTenantBinding.external_tenant_id == desired_external_tenant_id)
                .limit(1)
            )
            if conflict_binding is not None:
                abort(409, "external_tenant_id is already bound to another workspace.")

        tenant = TenantService.create_tenant(name=tenant_name, is_from_dashboard=True)

        if args.management_mode == ExternalManagementMode.EXTERNAL_MANAGED:
            assert desired_external_tenant_id is not None
            binding = ExternalTenantBinding(
                external_tenant_id=desired_external_tenant_id,
                tenant_id=tenant.id,
                source_version=0,
                management_mode=args.management_mode,
                allow_local_member_override=desired_allow_override,
                last_synced_at=naive_utc_now(),
            )
            db.session.add(binding)
            db.session.commit()

        default_tenant = TenantService.get_default_tenant()
        default_tenant_id = default_tenant.id if default_tenant else None
        created_binding = db.session.scalar(
            select(ExternalTenantBinding).where(ExternalTenantBinding.tenant_id == tenant.id).limit(1)
        )
        member_count = int(
            db.session.scalar(
                select(func.count(TenantAccountJoin.id)).where(TenantAccountJoin.tenant_id == tenant.id)
            )
            or 0
        )

        return {
            "result": "success",
            "tenant": _serialize_tenant_for_admin(
                tenant,
                default_tenant_id=default_tenant_id,
                binding=created_binding,
                member_count=member_count,
            ),
        }, 201
