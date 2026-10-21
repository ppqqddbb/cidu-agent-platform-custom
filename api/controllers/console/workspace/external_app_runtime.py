"""Runtime gateway endpoints for tenant external app API invocation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import timedelta
from math import ceil

from flask import abort, request
from flask_restx import Resource
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    capability_required,
    setup_required,
)
from core.tools.builtin_tool.providers.external_app_runtime.tools import runtime_common
from core.tools.errors import ToolInvokeError
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from libs.login import current_account_with_tenant, login_required
from models import OperationLog
from models.account import Account

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"
RUNTIME_AUDIT_ACTION = "external_app_runtime.invoke"
DEFAULT_AUDIT_WINDOW_HOURS = 24
DEFAULT_AUDIT_TOP_N = 10
DEFAULT_RECORDS_PAGE = 1
DEFAULT_RECORDS_PAGE_SIZE = 20
MAX_RECORDS_PAGE_SIZE = 200
MAX_AUDIT_WINDOW_HOURS = 24 * 30
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}

RUNTIME_PERMISSION_USER_SCOPED = runtime_common.RUNTIME_PERMISSION_USER_SCOPED
RUNTIME_PERMISSION_TENANT_SCOPED = runtime_common.RUNTIME_PERMISSION_TENANT_SCOPED
RUNTIME_PERMISSION_UNVERIFIED = runtime_common.RUNTIME_PERMISSION_UNVERIFIED


class RuntimeListAvailableApisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=255)
    context_token: str | None = Field(default=None, min_length=1, max_length=8192)
    max_results: int = Field(default=200, ge=1, le=1000)


class RuntimeInvokeApiPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(..., min_length=1, max_length=255)
    api_id: str = Field(..., min_length=1, max_length=255)
    context_token: str | None = Field(default=None, min_length=1, max_length=8192)
    params: dict[str, object] = Field(default_factory=dict)
    dry_run: bool = True
    timeout_seconds: float | None = Field(default=None, gt=0.0, le=120.0)


def reg(cls: type[BaseModel]):
    console_ns.schema_model(cls.__name__, cls.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0))


reg(RuntimeListAvailableApisPayload)
reg(RuntimeInvokeApiPayload)


def _resolve_permission(
    *,
    required_permissions: list[str],
    context_capabilities: list[str],
    token_verified: bool,
    call_mode: str = runtime_common.RUNTIME_CALL_MODE_GATEWAY,
) -> tuple[bool, str, list[str]]:
    return runtime_common.resolve_permission(
        required_permissions=required_permissions,
        context_capabilities=context_capabilities,
        token_verified=token_verified,
        call_mode=call_mode,
    )


def _build_invoke_credential_auth(
    *,
    app: object,
    timeout_seconds: float,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    return runtime_common._build_invoke_credential_auth(app=app, timeout_seconds=timeout_seconds)


def _ensure_account_and_tenant() -> tuple[Account, str]:
    current_user, current_tenant_id = current_account_with_tenant()
    if not isinstance(current_user, Account):
        abort(401, "Unauthorized.")
    if not current_tenant_id:
        abort(400, "No current tenant.")
    return current_user, current_tenant_id


def _runtime_error_status(message: str) -> int:
    if message in {
        "context_token is required by configuration.",
        "context_token has expired.",
        "context_token signature is invalid.",
        "context_token is invalid.",
        "context_token payload must be an object.",
    }:
        return 401

    if message in {
        "context_token tenant_id does not match current workspace.",
        "Current auth context does not satisfy required_permissions.",
    }:
        return 403

    if message.startswith("External app not found") or message.startswith("External app api not found"):
        return 404

    if (
        message.startswith("Failed to invoke external app api.")
        or message.startswith("OAuth token endpoint")
        or message.startswith("Failed to fetch OAuth2")
    ):
        return 502

    return 400


def _abort_for_runtime_error(error: ToolInvokeError) -> None:
    message = str(error) or "runtime invoke failed"
    abort(_runtime_error_status(message), message)


def _parse_positive_int_query_arg(*, name: str, default: int, maximum: int | None = None) -> int:
    raw_value = request.args.get(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        abort(400, f"{name} must be an integer.")
    if value < 1:
        abort(400, f"{name} must be >= 1.")
    if maximum is not None:
        return min(value, maximum)
    return value


def _parse_bool_query_arg(*, name: str, default: bool) -> bool:
    raw_value = request.args.get(name)
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    abort(400, f"{name} must be a boolean value.")


def _get_log_content(log: OperationLog) -> dict[str, object]:
    if isinstance(log.content, Mapping):
        return dict(log.content)
    return {}


def _parse_warnings(content: Mapping[str, object]) -> list[str]:
    raw_warnings = content.get("warnings")
    if not isinstance(raw_warnings, list):
        return []
    return [item for item in raw_warnings if isinstance(item, str)]


def _extract_failure_reason(content: Mapping[str, object]) -> str | None:
    for warning in _parse_warnings(content):
        if warning.startswith("request_error:"):
            return warning
        if warning.startswith("business_error:"):
            return warning

    if content.get("business_failed") is True:
        business_message = content.get("business_message")
        if isinstance(business_message, str) and business_message.strip():
            return f"business_error:{business_message.strip()}"
        business_code = content.get("business_code")
        if isinstance(business_code, (int, float)):
            return f"business_code:{int(business_code)}"
        if isinstance(business_code, str) and business_code.strip():
            return f"business_code:{business_code.strip()}"
        return "business_error"

    response_status = content.get("response_status")
    if isinstance(response_status, (int, float)) and int(response_status) >= 400:
        return f"response_status:{int(response_status)}"

    return None


def _extract_invoke_from(content: Mapping[str, object]) -> str:
    raw_value = content.get("invoke_from")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    return "unknown"


def _extract_latency_ms(content: Mapping[str, object]) -> float | None:
    raw_latency = content.get("latency_ms")
    if isinstance(raw_latency, (int, float)) and float(raw_latency) >= 0:
        return float(raw_latency)
    return None


def _calculate_p95(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(0, ceil(len(sorted_values) * 0.95) - 1)
    return round(sorted_values[index], 2)


def _query_runtime_audit_logs(
    *,
    tenant_id: str,
    window_hours: int,
    app_id: str | None,
    api_id: str | None,
    invoke_from: str | None,
) -> list[OperationLog]:
    start_time = naive_utc_now() - timedelta(hours=window_hours)
    logs = list(
        db.session.scalars(
            select(OperationLog)
            .where(
                OperationLog.tenant_id == tenant_id,
                OperationLog.action == RUNTIME_AUDIT_ACTION,
                OperationLog.created_at >= start_time,
            )
            .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        ).all()
    )

    filtered_logs: list[OperationLog] = []
    for log in logs:
        content = _get_log_content(log)
        if app_id and content.get("app_id") != app_id:
            continue
        if api_id and content.get("api_id") != api_id:
            continue
        if invoke_from and _extract_invoke_from(content) != invoke_from:
            continue
        filtered_logs.append(log)
    return filtered_logs


def _build_audit_summary(
    *,
    logs: list[OperationLog],
    window_hours: int,
    top_n: int,
) -> dict[str, object]:
    total_calls = len(logs)
    source_counter: Counter[str] = Counter()
    failure_counter: Counter[str] = Counter()
    api_stats: dict[tuple[str, str], dict[str, object]] = {}

    failed_calls = 0
    dry_run_calls = 0
    for log in logs:
        content = _get_log_content(log)
        source_counter[_extract_invoke_from(content)] += 1

        dry_run = bool(content.get("dry_run"))
        if dry_run:
            dry_run_calls += 1

        failure_reason = _extract_failure_reason(content)
        if failure_reason:
            failed_calls += 1
            failure_counter[failure_reason] += 1

        app_id = content.get("app_id")
        api_id = content.get("api_id")
        if not isinstance(app_id, str) or not app_id or not isinstance(api_id, str) or not api_id:
            continue

        stat_key = (app_id, api_id)
        stat = api_stats.setdefault(
            stat_key,
            {
                "app_id": app_id,
                "api_id": api_id,
                "total_calls": 0,
                "failed_calls": 0,
                "latency_values": [],
            },
        )
        stat["total_calls"] = int(stat["total_calls"]) + 1
        if failure_reason:
            stat["failed_calls"] = int(stat["failed_calls"]) + 1
        latency = _extract_latency_ms(content)
        if latency is not None:
            stat["latency_values"].append(latency)

    success_calls = total_calls - failed_calls
    error_rate = round((failed_calls / total_calls), 4) if total_calls else 0.0

    api_health: list[dict[str, object]] = []
    for stat in api_stats.values():
        total = int(stat["total_calls"])
        failed = int(stat["failed_calls"])
        current_error_rate = round((failed / total), 4) if total else 0.0
        if current_error_rate <= 0.05:
            health = "healthy"
        elif current_error_rate <= 0.2:
            health = "warning"
        else:
            health = "critical"

        api_health.append(
            {
                "app_id": stat["app_id"],
                "api_id": stat["api_id"],
                "total_calls": total,
                "failed_calls": failed,
                "error_rate": current_error_rate,
                "health": health,
                "p95_latency_ms": _calculate_p95(stat["latency_values"]),
            }
        )

    api_health.sort(
        key=lambda item: (
            -float(item["error_rate"]),
            -int(item["total_calls"]),
            str(item["app_id"]),
            str(item["api_id"]),
        )
    )

    return {
        "summary": {
            "window_hours": window_hours,
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": failed_calls,
            "dry_run_calls": dry_run_calls,
            "error_rate": error_rate,
            "source_breakdown": dict(source_counter),
        },
        "failure_reasons": [
            {"reason": reason, "count": count}
            for reason, count in failure_counter.most_common(top_n)
        ],
        "api_health": api_health[:top_n],
    }


def _serialize_runtime_audit_record(log: OperationLog) -> dict[str, object]:
    content = _get_log_content(log)
    failure_reason = _extract_failure_reason(content)
    response_status = content.get("response_status")
    normalized_response_status = int(response_status) if isinstance(response_status, (int, float)) else None
    return {
        "id": log.id,
        "tenant_id": log.tenant_id,
        "account_id": log.account_id,
        "created_at": int(log.created_at.timestamp()) if log.created_at else None,
        "created_ip": log.created_ip,
        "trace_id": content.get("trace_id"),
        "app_id": content.get("app_id"),
        "api_id": content.get("api_id"),
        "dry_run": bool(content.get("dry_run")),
        "invoke_from": _extract_invoke_from(content),
        "permission_level_actual": content.get("permission_level_actual"),
        "call_mode_actual": content.get("call_mode_actual"),
        "response_status": normalized_response_status,
        "warnings": _parse_warnings(content),
        "failed": failure_reason is not None,
        "failure_reason": failure_reason,
    }


@console_ns.route("/workspaces/current/external-apps/runtime/available-apis")
class ExternalAppRuntimeAvailableApisApi(Resource):
    @console_ns.expect(console_ns.models[RuntimeListAvailableApisPayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def post(self):
        _, tenant_id = _ensure_account_and_tenant()
        payload = RuntimeListAvailableApisPayload.model_validate(console_ns.payload or {})

        try:
            result = runtime_common.list_available_apis(
                tenant_id=tenant_id,
                query=payload.query,
                context_token=payload.context_token,
                max_results=payload.max_results,
                only_allowed=False,
            )
        except ToolInvokeError as exc:
            _abort_for_runtime_error(exc)
        return result, 200


@console_ns.route("/workspaces/current/external-apps/runtime/invoke")
class ExternalAppRuntimeInvokeApi(Resource):
    @console_ns.expect(console_ns.models[RuntimeInvokeApiPayload.__name__])
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def post(self):
        current_user, tenant_id = _ensure_account_and_tenant()
        payload = RuntimeInvokeApiPayload.model_validate(console_ns.payload or {})

        try:
            result = runtime_common.invoke_api(
                tenant_id=tenant_id,
                account_id=current_user.id,
                app_id=payload.app_id,
                api_id=payload.api_id,
                context_token=payload.context_token,
                params=payload.params,
                dry_run=payload.dry_run,
                timeout_seconds=payload.timeout_seconds,
                invoke_from="console_runtime",
                created_ip=request.remote_addr or "0.0.0.0",
            )
        except ToolInvokeError as exc:
            _abort_for_runtime_error(exc)
        return result, 200


@console_ns.route("/workspaces/current/external-apps/runtime/audit/summary")
class ExternalAppRuntimeAuditSummaryApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self):
        _, tenant_id = _ensure_account_and_tenant()
        window_hours = _parse_positive_int_query_arg(
            name="window_hours",
            default=DEFAULT_AUDIT_WINDOW_HOURS,
            maximum=MAX_AUDIT_WINDOW_HOURS,
        )
        top_n = _parse_positive_int_query_arg(name="top_n", default=DEFAULT_AUDIT_TOP_N, maximum=100)
        app_id = request.args.get("app_id", "").strip() or None
        api_id = request.args.get("api_id", "").strip() or None
        invoke_from = request.args.get("invoke_from", "").strip() or None

        logs = _query_runtime_audit_logs(
            tenant_id=tenant_id,
            window_hours=window_hours,
            app_id=app_id,
            api_id=api_id,
            invoke_from=invoke_from,
        )
        return _build_audit_summary(logs=logs, window_hours=window_hours, top_n=top_n), 200


@console_ns.route("/workspaces/current/external-apps/runtime/audit/records")
class ExternalAppRuntimeAuditRecordsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_required("workspace.view")
    def get(self):
        _, tenant_id = _ensure_account_and_tenant()
        window_hours = _parse_positive_int_query_arg(
            name="window_hours",
            default=DEFAULT_AUDIT_WINDOW_HOURS,
            maximum=MAX_AUDIT_WINDOW_HOURS,
        )
        page = _parse_positive_int_query_arg(name="page", default=DEFAULT_RECORDS_PAGE)
        page_size = _parse_positive_int_query_arg(
            name="page_size",
            default=DEFAULT_RECORDS_PAGE_SIZE,
            maximum=MAX_RECORDS_PAGE_SIZE,
        )
        app_id = request.args.get("app_id", "").strip() or None
        api_id = request.args.get("api_id", "").strip() or None
        invoke_from = request.args.get("invoke_from", "").strip() or None
        include_dry_run = _parse_bool_query_arg(name="include_dry_run", default=True)
        outcome = request.args.get("outcome", "all").strip().lower()
        if outcome not in {"all", "success", "failure"}:
            abort(400, "outcome must be one of: all, success, failure.")

        logs = _query_runtime_audit_logs(
            tenant_id=tenant_id,
            window_hours=window_hours,
            app_id=app_id,
            api_id=api_id,
            invoke_from=invoke_from,
        )

        filtered_logs: list[OperationLog] = []
        for log in logs:
            content = _get_log_content(log)
            is_dry_run = bool(content.get("dry_run"))
            if not include_dry_run and is_dry_run:
                continue

            failure_reason = _extract_failure_reason(content)
            if outcome == "success" and failure_reason is not None:
                continue
            if outcome == "failure" and failure_reason is None:
                continue
            filtered_logs.append(log)

        total = len(filtered_logs)
        offset = (page - 1) * page_size
        page_logs = filtered_logs[offset : offset + page_size]

        return {
            "records": [_serialize_runtime_audit_record(log) for log in page_logs],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": offset + len(page_logs) < total,
            },
        }, 200
