"""Console APIs for tenant-scoped external application and interface management.

This module exposes CRUD endpoints for third-party app registrations and API
definitions under the current workspace tenant. It also provides an OpenAPI
import endpoint to bootstrap interface metadata before manual confirmation.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime

from flask import abort, request
from flask_restx import Resource
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
from models import (
    TenantExternalApp,
    TenantExternalAppApi,
    TenantExternalAppApiSource,
    TenantExternalAppAuthMode,
)
from models.account import Account

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
EXTERNAL_APP_CALL_MODE_GATEWAY = "gateway"
EXTERNAL_APP_CALL_MODE_DIRECT = "direct"
EXTERNAL_APP_CALL_MODES = {
    EXTERNAL_APP_CALL_MODE_GATEWAY,
    EXTERNAL_APP_CALL_MODE_DIRECT,
}
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
DEFAULT_CREDENTIAL_ALERT_WITHIN_HOURS = 72
MAX_CREDENTIAL_ALERT_WITHIN_HOURS = 24 * 30

logger = logging.getLogger(__name__)


class ExternalAppCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    app_purpose: str | None = Field(default=None, max_length=4000)
    call_mode: str = Field(default=EXTERNAL_APP_CALL_MODE_GATEWAY, min_length=1, max_length=32)
    auth_mode: TenantExternalAppAuthMode = TenantExternalAppAuthMode.NONE
    auth_config: dict[str, object] = Field(default_factory=dict)
    is_enabled: bool = True

    @field_validator("call_mode")
    @classmethod
    def validate_call_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in EXTERNAL_APP_CALL_MODES:
            raise ValueError(f"Unsupported call_mode: {value}")
        return normalized


class ExternalAppUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    app_purpose: str | None = Field(default=None, max_length=4000)
    call_mode: str | None = Field(default=None, min_length=1, max_length=32)
    auth_mode: TenantExternalAppAuthMode | None = None
    auth_config: dict[str, object] | None = None
    is_enabled: bool | None = None

    @field_validator("call_mode")
    @classmethod
    def validate_call_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in EXTERNAL_APP_CALL_MODES:
            raise ValueError(f"Unsupported call_mode: {value}")
        return normalized


class ExternalAppApiCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    http_method: str = Field(..., min_length=1, max_length=16)
    path: str = Field(..., min_length=1, max_length=1024)
    summary: str | None = Field(default=None, max_length=1024)
    description: str | None = Field(default=None, max_length=4000)
    api_purpose: str | None = Field(default=None, max_length=4000)
    required_permissions: list[str] = Field(default_factory=list)
    request_schema: dict[str, object] = Field(default_factory=dict)
    response_schema: dict[str, object] = Field(default_factory=dict)
    is_confirmed: bool = True
    is_enabled: bool = True

    @field_validator("http_method")
    @classmethod
    def validate_http_method(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in HTTP_METHODS:
            raise ValueError(f"Unsupported http_method: {value}")
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("path must start with '/'.")
        return normalized


class ExternalAppApiUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    http_method: str | None = Field(default=None, min_length=1, max_length=16)
    path: str | None = Field(default=None, min_length=1, max_length=1024)
    summary: str | None = Field(default=None, max_length=1024)
    description: str | None = Field(default=None, max_length=4000)
    api_purpose: str | None = Field(default=None, max_length=4000)
    required_permissions: list[str] | None = None
    request_schema: dict[str, object] | None = None
    response_schema: dict[str, object] | None = None
    is_confirmed: bool | None = None
    is_enabled: bool | None = None

    @field_validator("http_method")
    @classmethod
    def validate_http_method(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in HTTP_METHODS:
            raise ValueError(f"Unsupported http_method: {value}")
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("path must start with '/'.")
        return normalized


class OpenAPIImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: dict[str, object] | str
    overwrite_existing: bool = True
    import_as_unconfirmed: bool = True
    source_version: int | None = Field(default=None, ge=1)


def reg(cls: type[BaseModel]):
    console_ns.schema_model(cls.__name__, cls.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0))


reg(ExternalAppCreatePayload)
reg(ExternalAppUpdatePayload)
reg(ExternalAppApiCreatePayload)
reg(ExternalAppApiUpdatePayload)
reg(OpenAPIImportPayload)


def _ensure_account_and_tenant() -> tuple[Account, str]:
    current_user, current_tenant_id = current_account_with_tenant()
    if not isinstance(current_user, Account):
        abort(401, "Unauthorized.")
    if not current_tenant_id:
        abort(400, "No current tenant.")
    return current_user, current_tenant_id


def _serialize_external_app(app: TenantExternalApp, *, api_count: int | None = None) -> dict[str, object]:
    call_mode = _extract_call_mode_from_auth_config(app.auth_config)
    payload: dict[str, object] = {
        "id": app.id,
        "tenant_id": app.tenant_id,
        "name": app.name,
        "description": app.description,
        "app_purpose": app.app_purpose,
        "call_mode": call_mode,
        "auth_mode": app.auth_mode.value if hasattr(app.auth_mode, "value") else str(app.auth_mode),
        "auth_config": app.auth_config,
        "is_enabled": app.is_enabled,
        "created_at": int(app.created_at.timestamp()) if app.created_at else None,
        "updated_at": int(app.updated_at.timestamp()) if app.updated_at else None,
    }
    if api_count is not None:
        payload["api_count"] = api_count
    return payload


def _serialize_external_app_api(item: TenantExternalAppApi) -> dict[str, object]:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "app_id": item.app_id,
        "name": item.name,
        "http_method": item.http_method,
        "path": item.path,
        "summary": item.summary,
        "description": item.description,
        "api_purpose": item.api_purpose,
        "source": item.source.value if hasattr(item.source, "value") else str(item.source),
        "source_version": item.source_version,
        "required_permissions": item.required_permissions,
        "request_schema": item.request_schema,
        "response_schema": item.response_schema,
        "is_confirmed": item.is_confirmed,
        "is_enabled": item.is_enabled,
        "imported_at": int(item.imported_at.timestamp()) if item.imported_at else None,
        "created_at": int(item.created_at.timestamp()) if item.created_at else None,
        "updated_at": int(item.updated_at.timestamp()) if item.updated_at else None,
    }


def _get_external_app_or_404(*, tenant_id: str, app_id: str) -> TenantExternalApp:
    app = db.session.scalar(
        select(TenantExternalApp)
        .where(TenantExternalApp.id == app_id, TenantExternalApp.tenant_id == tenant_id)
        .limit(1)
    )
    if app is None:
        abort(404, "External app not found.")
    return app


def _get_external_app_api_or_404(*, tenant_id: str, app_id: str, api_id: str) -> TenantExternalAppApi:
    item = db.session.scalar(
        select(TenantExternalAppApi)
        .where(
            TenantExternalAppApi.id == api_id,
            TenantExternalAppApi.app_id == app_id,
            TenantExternalAppApi.tenant_id == tenant_id,
        )
        .limit(1)
    )
    if item is None:
        abort(404, "External app api not found.")
    return item


def _extract_json_object(value: object, *, field_name: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            abort(400, f"{field_name} must be valid JSON text. {exc}")
        if not isinstance(parsed, dict):
            abort(400, f"{field_name} must be a JSON object.")
        return parsed
    abort(400, f"{field_name} must be a JSON object or JSON text.")


def _extract_call_mode_from_auth_config(auth_config: object) -> str:
    if isinstance(auth_config, Mapping):
        raw_call_mode = auth_config.get("call_mode")
        if isinstance(raw_call_mode, str):
            normalized_call_mode = raw_call_mode.strip().lower()
            if normalized_call_mode in EXTERNAL_APP_CALL_MODES:
                return normalized_call_mode
    return EXTERNAL_APP_CALL_MODE_GATEWAY


def _parse_positive_int_query_arg(*, name: str, default: int, maximum: int | None = None) -> int:
    raw_value = request.args.get(name)
    if raw_value is None or not str(raw_value).strip():
        value = default
    else:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            abort(400, f"{name} must be an integer.")

    if value < 1:
        abort(400, f"{name} must be >= 1.")
    if maximum is not None:
        return min(value, maximum)
    return value


def _extract_api_risk_reasons(*, app: TenantExternalApp, api_item: TenantExternalAppApi) -> list[str]:
    reasons: list[str] = []
    if _extract_call_mode_from_auth_config(app.auth_config) == EXTERNAL_APP_CALL_MODE_DIRECT:
        reasons.append("direct_call_mode")
    if bool(api_item.required_permissions):
        reasons.append("required_permissions_present")
    if api_item.http_method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        reasons.append("write_operation")
    if not api_item.is_confirmed:
        reasons.append("api_not_confirmed")
    return reasons


def _parse_expire_timestamp_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        ts = int(value)
        return ts if ts > 0 else None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            ts = int(normalized)
            return ts if ts > 0 else None
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp())

    return None


def _extract_auth_expire_at(auth_config: object) -> int | None:
    if not isinstance(auth_config, Mapping):
        return None

    for key in ("expires_at", "credential_expires_at", "token_expires_at"):
        expire_at = _parse_expire_timestamp_value(auth_config.get(key))
        if expire_at is not None:
            return expire_at

    return None


def _build_credential_alert_level(remaining_seconds: int) -> str:
    if remaining_seconds <= 0:
        return "expired"
    if remaining_seconds <= 6 * 3600:
        return "critical"
    if remaining_seconds <= 24 * 3600:
        return "warning"
    return "info"


def _parse_pagination_args() -> tuple[int, int]:
    raw_page = request.args.get("page", str(DEFAULT_PAGE))
    raw_page_size = request.args.get("page_size", str(DEFAULT_PAGE_SIZE))

    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        abort(400, "page must be an integer.")
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        abort(400, "page_size must be an integer.")

    if page < 1:
        abort(400, "page must be >= 1.")
    if page_size < 1:
        abort(400, "page_size must be >= 1.")

    return page, min(page_size, MAX_PAGE_SIZE)


@console_ns.route("/workspaces/current/external-apps")
class ExternalAppListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self):
        _, tenant_id = _ensure_account_and_tenant()
        page, page_size = _parse_pagination_args()
        query = request.args.get("query", "").strip()

        count_stmt = select(func.count(TenantExternalApp.id)).where(TenantExternalApp.tenant_id == tenant_id)
        list_stmt = (
            select(TenantExternalApp)
            .where(TenantExternalApp.tenant_id == tenant_id)
            .order_by(TenantExternalApp.created_at.desc(), TenantExternalApp.id.desc())
        )
        if query:
            pattern = f"%{query}%"
            count_stmt = count_stmt.where(TenantExternalApp.name.ilike(pattern))
            list_stmt = list_stmt.where(TenantExternalApp.name.ilike(pattern))

        total = int(db.session.scalar(count_stmt) or 0)
        offset = (page - 1) * page_size
        apps = list(db.session.scalars(list_stmt.limit(page_size).offset(offset)).all())
        if not apps:
            return {
                "apps": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "has_more": False,
                },
            }, 200

        app_ids = [item.id for item in apps]
        rows = db.session.execute(
            select(TenantExternalAppApi.app_id, func.count(TenantExternalAppApi.id))
            .where(TenantExternalAppApi.tenant_id == tenant_id, TenantExternalAppApi.app_id.in_(app_ids))
            .group_by(TenantExternalAppApi.app_id)
        )
        api_count_by_app_id = {app_id: int(count) for app_id, count in rows}

        return {
            "apps": [
                _serialize_external_app(item, api_count=api_count_by_app_id.get(item.id, 0))
                for item in apps
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": offset + len(apps) < total,
            },
        }, 200

    @console_ns.expect(console_ns.models[ExternalAppCreatePayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def post(self):
        current_user, tenant_id = _ensure_account_and_tenant()
        payload = ExternalAppCreatePayload.model_validate(console_ns.payload or {})

        normalized_name = payload.name.strip()
        if not normalized_name:
            abort(400, "name is required.")

        existing = db.session.scalar(
            select(TenantExternalApp)
            .where(TenantExternalApp.tenant_id == tenant_id, TenantExternalApp.name == normalized_name)
            .limit(1)
        )
        if existing is not None:
            abort(409, "External app name already exists in current workspace.")

        app = TenantExternalApp(
            tenant_id=tenant_id,
            name=normalized_name,
            description=payload.description.strip() if payload.description else None,
            app_purpose=payload.app_purpose.strip() if payload.app_purpose else None,
            auth_mode=payload.auth_mode,
            auth_config={
                **payload.auth_config,
                "call_mode": payload.call_mode,
            },
            is_enabled=payload.is_enabled,
            created_by_account_id=current_user.id,
            updated_by_account_id=current_user.id,
        )
        db.session.add(app)
        db.session.commit()
        return {"result": "success", "app": _serialize_external_app(app, api_count=0)}, 201


@console_ns.route("/workspaces/current/external-apps/<string:app_id>")
class ExternalAppItemApi(Resource):
    @console_ns.expect(console_ns.models[ExternalAppUpdatePayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def put(self, app_id: str):
        current_user, tenant_id = _ensure_account_and_tenant()
        payload = ExternalAppUpdatePayload.model_validate(console_ns.payload or {})
        app = _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)

        if payload.name is not None:
            normalized_name = payload.name.strip()
            if not normalized_name:
                abort(400, "name cannot be empty.")
            conflict = db.session.scalar(
                select(TenantExternalApp)
                .where(
                    TenantExternalApp.tenant_id == tenant_id,
                    TenantExternalApp.name == normalized_name,
                    TenantExternalApp.id != app.id,
                )
                .limit(1)
            )
            if conflict is not None:
                abort(409, "External app name already exists in current workspace.")
            app.name = normalized_name

        if payload.description is not None:
            app.description = payload.description.strip() if payload.description else None
        if payload.app_purpose is not None:
            app.app_purpose = payload.app_purpose.strip() if payload.app_purpose else None
        if payload.auth_mode is not None:
            app.auth_mode = payload.auth_mode
        if payload.auth_config is not None or payload.call_mode is not None:
            next_auth_config: dict[str, object]
            if payload.auth_config is not None:
                next_auth_config = dict(payload.auth_config)
            else:
                next_auth_config = dict(app.auth_config)

            if payload.call_mode is not None:
                next_auth_config["call_mode"] = payload.call_mode
            elif "call_mode" not in next_auth_config:
                next_auth_config["call_mode"] = _extract_call_mode_from_auth_config(app.auth_config)
            app.auth_config = next_auth_config
        if payload.is_enabled is not None:
            app.is_enabled = payload.is_enabled

        app.updated_by_account_id = current_user.id
        db.session.commit()

        api_count = int(
            db.session.scalar(
                select(func.count(TenantExternalAppApi.id)).where(
                    TenantExternalAppApi.tenant_id == tenant_id,
                    TenantExternalAppApi.app_id == app.id,
                )
            )
            or 0
        )
        return {"result": "success", "app": _serialize_external_app(app, api_count=api_count)}, 200

    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def delete(self, app_id: str):
        _, tenant_id = _ensure_account_and_tenant()
        app = _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)

        db.session.query(TenantExternalAppApi).filter(
            TenantExternalAppApi.tenant_id == tenant_id,
            TenantExternalAppApi.app_id == app.id,
        ).delete(synchronize_session=False)
        db.session.delete(app)
        db.session.commit()
        return {"result": "success"}, 200


@console_ns.route("/workspaces/current/external-apps/<string:app_id>/apis")
class ExternalAppApiListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self, app_id: str):
        _, tenant_id = _ensure_account_and_tenant()
        _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)
        page, page_size = _parse_pagination_args()
        query = request.args.get("query", "").strip()

        count_stmt = select(func.count(TenantExternalAppApi.id)).where(
            TenantExternalAppApi.tenant_id == tenant_id,
            TenantExternalAppApi.app_id == app_id,
        )
        list_stmt = (
            select(TenantExternalAppApi)
            .where(TenantExternalAppApi.tenant_id == tenant_id, TenantExternalAppApi.app_id == app_id)
            .order_by(
                TenantExternalAppApi.http_method.asc(),
                TenantExternalAppApi.path.asc(),
                TenantExternalAppApi.id.asc(),
            )
        )
        if query:
            pattern = f"%{query}%"
            search_filter = (
                TenantExternalAppApi.name.ilike(pattern)
                | TenantExternalAppApi.path.ilike(pattern)
                | TenantExternalAppApi.http_method.ilike(pattern)
            )
            count_stmt = count_stmt.where(search_filter)
            list_stmt = list_stmt.where(search_filter)

        total = int(db.session.scalar(count_stmt) or 0)
        offset = (page - 1) * page_size
        apis = list(db.session.scalars(list_stmt.limit(page_size).offset(offset)).all())
        return {
            "apis": [_serialize_external_app_api(item) for item in apis],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": offset + len(apis) < total,
            },
        }, 200

    @console_ns.expect(console_ns.models[ExternalAppApiCreatePayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def post(self, app_id: str):
        current_user, tenant_id = _ensure_account_and_tenant()
        _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)

        payload = ExternalAppApiCreatePayload.model_validate(console_ns.payload or {})
        conflict = db.session.scalar(
            select(TenantExternalAppApi)
            .where(
                TenantExternalAppApi.tenant_id == tenant_id,
                TenantExternalAppApi.app_id == app_id,
                TenantExternalAppApi.http_method == payload.http_method,
                TenantExternalAppApi.path == payload.path,
            )
            .limit(1)
        )
        if conflict is not None:
            abort(409, "External app api already exists.")

        item = TenantExternalAppApi(
            tenant_id=tenant_id,
            app_id=app_id,
            name=payload.name.strip(),
            http_method=payload.http_method,
            path=payload.path,
            summary=payload.summary.strip() if payload.summary else None,
            description=payload.description.strip() if payload.description else None,
            api_purpose=payload.api_purpose.strip() if payload.api_purpose else None,
            source=TenantExternalAppApiSource.MANUAL,
            source_version=1,
            required_permissions=payload.required_permissions,
            request_schema=payload.request_schema,
            response_schema=payload.response_schema,
            is_confirmed=payload.is_confirmed,
            is_enabled=payload.is_enabled,
            created_by_account_id=current_user.id,
            updated_by_account_id=current_user.id,
            imported_at=naive_utc_now(),
        )
        db.session.add(item)
        db.session.commit()
        return {"result": "success", "api": _serialize_external_app_api(item)}, 201


@console_ns.route("/workspaces/current/external-apps/<string:app_id>/apis/<string:api_id>")
class ExternalAppApiItemApi(Resource):
    @console_ns.expect(console_ns.models[ExternalAppApiUpdatePayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def put(self, app_id: str, api_id: str):
        current_user, tenant_id = _ensure_account_and_tenant()
        _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)
        item = _get_external_app_api_or_404(tenant_id=tenant_id, app_id=app_id, api_id=api_id)
        payload = ExternalAppApiUpdatePayload.model_validate(console_ns.payload or {})

        next_method = payload.http_method or item.http_method
        next_path = payload.path or item.path
        if next_method != item.http_method or next_path != item.path:
            conflict = db.session.scalar(
                select(TenantExternalAppApi)
                .where(
                    TenantExternalAppApi.tenant_id == tenant_id,
                    TenantExternalAppApi.app_id == app_id,
                    TenantExternalAppApi.http_method == next_method,
                    TenantExternalAppApi.path == next_path,
                    TenantExternalAppApi.id != item.id,
                )
                .limit(1)
            )
            if conflict is not None:
                abort(409, "External app api already exists.")

        if payload.name is not None:
            normalized_name = payload.name.strip()
            if not normalized_name:
                abort(400, "name cannot be empty.")
            item.name = normalized_name
        if payload.http_method is not None:
            item.http_method = payload.http_method
        if payload.path is not None:
            item.path = payload.path
        if payload.summary is not None:
            item.summary = payload.summary.strip() if payload.summary else None
        if payload.description is not None:
            item.description = payload.description.strip() if payload.description else None
        if payload.api_purpose is not None:
            item.api_purpose = payload.api_purpose.strip() if payload.api_purpose else None
        if payload.required_permissions is not None:
            item.required_permissions = payload.required_permissions
        if payload.request_schema is not None:
            item.request_schema = payload.request_schema
        if payload.response_schema is not None:
            item.response_schema = payload.response_schema
        if payload.is_confirmed is not None:
            item.is_confirmed = payload.is_confirmed
        if payload.is_enabled is not None:
            item.is_enabled = payload.is_enabled

        item.updated_by_account_id = current_user.id
        db.session.commit()
        return {"result": "success", "api": _serialize_external_app_api(item)}, 200

    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def delete(self, app_id: str, api_id: str):
        _, tenant_id = _ensure_account_and_tenant()
        _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)
        item = _get_external_app_api_or_404(tenant_id=tenant_id, app_id=app_id, api_id=api_id)
        db.session.delete(item)
        db.session.commit()
        return {"result": "success"}, 200


@console_ns.route("/workspaces/current/external-apps/<string:app_id>/openapi/import")
class ExternalAppOpenAPIImportApi(Resource):
    @console_ns.expect(console_ns.models[OpenAPIImportPayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.settings.update")
    def post(self, app_id: str):
        current_user, tenant_id = _ensure_account_and_tenant()
        _get_external_app_or_404(tenant_id=tenant_id, app_id=app_id)
        payload = OpenAPIImportPayload.model_validate(console_ns.payload or {})
        spec = _extract_json_object(payload.spec, field_name="spec")

        paths = spec.get("paths")
        if not isinstance(paths, Mapping):
            abort(400, "OpenAPI spec must include object field: paths.")

        source_version = payload.source_version or int(naive_utc_now().timestamp())
        default_confirmed = not payload.import_as_unconfirmed

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for raw_path, path_item in paths.items():
            if not isinstance(raw_path, str) or not raw_path.startswith("/"):
                skipped_count += 1
                continue
            if not isinstance(path_item, Mapping):
                skipped_count += 1
                continue

            for raw_method, operation in path_item.items():
                if not isinstance(raw_method, str):
                    skipped_count += 1
                    continue
                method = raw_method.strip().upper()
                if method not in HTTP_METHODS:
                    continue
                if not isinstance(operation, Mapping):
                    skipped_count += 1
                    continue

                operation_id = operation.get("operationId")
                summary = operation.get("summary")
                description = operation.get("description")
                api_purpose = operation.get("x-api-purpose")
                required_permissions = operation.get("x-required-permissions")
                if not isinstance(required_permissions, list):
                    required_permissions = []
                required_permissions = [str(item) for item in required_permissions if isinstance(item, str)]

                request_schema = operation.get("requestBody")
                response_schema = operation.get("responses")

                item_name = (
                    str(operation_id).strip()
                    if isinstance(operation_id, str) and operation_id.strip()
                    else (
                        str(summary).strip()
                        if isinstance(summary, str) and summary.strip()
                        else f"{method} {raw_path}"
                    )
                )

                existing = db.session.scalar(
                    select(TenantExternalAppApi)
                    .where(
                        TenantExternalAppApi.tenant_id == tenant_id,
                        TenantExternalAppApi.app_id == app_id,
                        TenantExternalAppApi.http_method == method,
                        TenantExternalAppApi.path == raw_path,
                    )
                    .limit(1)
                )

                if existing is not None and not payload.overwrite_existing:
                    skipped_count += 1
                    continue

                normalized_summary = summary.strip() if isinstance(summary, str) else None
                normalized_description = description.strip() if isinstance(description, str) else None
                normalized_api_purpose = api_purpose.strip() if isinstance(api_purpose, str) else None
                normalized_request_schema = request_schema if isinstance(request_schema, Mapping) else {}
                normalized_response_schema = response_schema if isinstance(response_schema, Mapping) else {}

                if existing is None:
                    db.session.add(
                        TenantExternalAppApi(
                            tenant_id=tenant_id,
                            app_id=app_id,
                            name=item_name,
                            http_method=method,
                            path=raw_path,
                            summary=normalized_summary,
                            description=normalized_description,
                            api_purpose=normalized_api_purpose,
                            source=TenantExternalAppApiSource.OPENAPI_IMPORT,
                            source_version=source_version,
                            required_permissions=required_permissions,
                            request_schema=dict(normalized_request_schema),
                            response_schema=dict(normalized_response_schema),
                            is_confirmed=default_confirmed,
                            is_enabled=True,
                            created_by_account_id=current_user.id,
                            updated_by_account_id=current_user.id,
                            imported_at=naive_utc_now(),
                        )
                    )
                    created_count += 1
                else:
                    existing.name = item_name
                    existing.summary = normalized_summary
                    existing.description = normalized_description
                    existing.api_purpose = normalized_api_purpose
                    existing.source = TenantExternalAppApiSource.OPENAPI_IMPORT
                    existing.source_version = source_version
                    existing.required_permissions = required_permissions
                    existing.request_schema = dict(normalized_request_schema)
                    existing.response_schema = dict(normalized_response_schema)
                    existing.is_confirmed = default_confirmed
                    existing.is_enabled = True
                    existing.updated_by_account_id = current_user.id
                    existing.imported_at = naive_utc_now()
                    updated_count += 1

        if created_count == 0 and updated_count == 0:
            logger.info("openapi import produced no api changes app_id=%s tenant_id=%s", app_id, tenant_id)
            abort(400, "No valid API operations found from the provided OpenAPI spec.")

        db.session.commit()
        return {
            "result": "success",
            "summary": {
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "source_version": source_version,
            },
        }, 200


@console_ns.route("/workspaces/current/external-apps/governance/risk-report")
class ExternalAppGovernanceRiskReportApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self):
        _, tenant_id = _ensure_account_and_tenant()

        apps = list(
            db.session.scalars(
                select(TenantExternalApp)
                .where(TenantExternalApp.tenant_id == tenant_id)
                .order_by(TenantExternalApp.created_at.desc(), TenantExternalApp.id.desc())
            ).all()
        )
        if not apps:
            return {
                "summary": {
                    "total_apps": 0,
                    "total_apis": 0,
                    "direct_mode_apps": 0,
                    "high_risk_api_candidates": 0,
                    "gateway_only_recommendations": 0,
                },
                "gateway_only_recommendations": [],
            }, 200

        app_by_id = {item.id: item for item in apps}
        api_items = list(
            db.session.scalars(
                select(TenantExternalAppApi)
                .where(
                    TenantExternalAppApi.tenant_id == tenant_id,
                    TenantExternalAppApi.app_id.in_(list(app_by_id.keys())),
                )
                .order_by(
                    TenantExternalAppApi.app_id.asc(),
                    TenantExternalAppApi.http_method.asc(),
                    TenantExternalAppApi.path.asc(),
                )
            ).all()
        )

        direct_mode_app_count = sum(
            1
            for item in apps
            if _extract_call_mode_from_auth_config(item.auth_config) == EXTERNAL_APP_CALL_MODE_DIRECT
        )
        high_risk_candidates = 0
        recommendations: list[dict[str, object]] = []
        for api_item in api_items:
            app = app_by_id.get(api_item.app_id)
            if app is None:
                continue

            reasons = _extract_api_risk_reasons(app=app, api_item=api_item)
            if not reasons:
                continue

            high_risk_candidates += 1
            if "direct_call_mode" not in reasons:
                continue

            recommendations.append(
                {
                    "app_id": app.id,
                    "app_name": app.name,
                    "api_id": api_item.id,
                    "api_name": api_item.name,
                    "http_method": api_item.http_method,
                    "path": api_item.path,
                    "risk_reasons": reasons,
                    "recommended_call_mode": EXTERNAL_APP_CALL_MODE_GATEWAY,
                }
            )

        return {
            "summary": {
                "total_apps": len(apps),
                "total_apis": len(api_items),
                "direct_mode_apps": direct_mode_app_count,
                "high_risk_api_candidates": high_risk_candidates,
                "gateway_only_recommendations": len(recommendations),
            },
            "gateway_only_recommendations": recommendations,
        }, 200


@console_ns.route("/workspaces/current/external-apps/governance/credential-alerts")
class ExternalAppGovernanceCredentialAlertsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self):
        _, tenant_id = _ensure_account_and_tenant()
        within_hours = _parse_positive_int_query_arg(
            name="within_hours",
            default=DEFAULT_CREDENTIAL_ALERT_WITHIN_HOURS,
            maximum=MAX_CREDENTIAL_ALERT_WITHIN_HOURS,
        )

        apps = list(
            db.session.scalars(
                select(TenantExternalApp)
                .where(TenantExternalApp.tenant_id == tenant_id)
                .order_by(TenantExternalApp.created_at.desc(), TenantExternalApp.id.desc())
            ).all()
        )

        now_ts = int(datetime.now(tz=UTC).timestamp())
        alert_threshold_seconds = within_hours * 3600
        alerts: list[dict[str, object]] = []
        for app in apps:
            expire_at = _extract_auth_expire_at(app.auth_config)
            if expire_at is None:
                continue

            remaining_seconds = int(expire_at - now_ts)
            if remaining_seconds > alert_threshold_seconds:
                continue

            alerts.append(
                {
                    "app_id": app.id,
                    "app_name": app.name,
                    "auth_mode": app.auth_mode.value if hasattr(app.auth_mode, "value") else str(app.auth_mode),
                    "credential_expires_at": expire_at,
                    "remaining_seconds": remaining_seconds,
                    "alert_level": _build_credential_alert_level(remaining_seconds),
                }
            )

        alerts.sort(key=lambda item: int(item["remaining_seconds"]))
        return {
            "summary": {
                "within_hours": within_hours,
                "total_alerts": len(alerts),
            },
            "alerts": alerts,
        }, 200
