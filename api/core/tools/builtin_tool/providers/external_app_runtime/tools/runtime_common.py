from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlparse
from uuid import uuid4

import jwt
from jwt import DecodeError, ExpiredSignatureError, InvalidSignatureError, InvalidTokenError
from sqlalchemy import select

from configs import dify_config
from core.helper.ssrf_proxy import ssrf_proxy
from core.model_manager import ModelManager
from core.tools.errors import ToolInvokeError
from extensions.ext_database import db
from graphon.model_runtime.entities.model_entities import ModelType
from models import OperationLog, TenantExternalApp, TenantExternalAppApi

RUNTIME_PERMISSION_USER_SCOPED = "user_scoped"
RUNTIME_PERMISSION_TENANT_SCOPED = "tenant_scoped"
RUNTIME_PERMISSION_UNVERIFIED = "unverified"
RUNTIME_CALL_MODE_GATEWAY = "gateway"
RUNTIME_CALL_MODE_DIRECT = "direct"
RUNTIME_CALL_MODES = {
    RUNTIME_CALL_MODE_GATEWAY,
    RUNTIME_CALL_MODE_DIRECT,
}

logger = logging.getLogger(__name__)

BUSINESS_ERROR_MESSAGE_HINTS = (
    "internal server error",
    "server error",
    "request failed",
    "failed",
    "error",
    "exception",
    "内部服务器错误",
    "系统错误",
    "服务异常",
    "失败",
    "错误",
)


REQUEST_PARAM_SECTIONS: tuple[str, str, str, str] = ("path", "query", "body", "headers")


def ensure_gateway_enabled() -> None:
    if not dify_config.EXTERNAL_APP_GATEWAY_ENABLED:
        raise ToolInvokeError("External app runtime gateway is disabled by configuration.")


def extract_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def extract_call_mode_from_auth_config(auth_config: object) -> str:
    if isinstance(auth_config, Mapping):
        raw_call_mode = auth_config.get("call_mode")
        if isinstance(raw_call_mode, str):
            normalized_call_mode = raw_call_mode.strip().lower()
            if normalized_call_mode in RUNTIME_CALL_MODES:
                return normalized_call_mode
    return RUNTIME_CALL_MODE_GATEWAY


def parse_runtime_context(*, tenant_id: str, context_token: str | None) -> tuple[dict[str, object], bool, list[str]]:
    warnings: list[str] = []
    if not context_token:
        if dify_config.EXTERNAL_APP_CONTEXT_TOKEN_REQUIRED:
            raise ToolInvokeError("context_token is required by configuration.")
        return {}, False, warnings

    token_secret = dify_config.EXTERNAL_APP_CONTEXT_TOKEN_SECRET
    if not token_secret:
        warnings.append("context_token_not_verified_missing_secret")
        return {}, False, warnings

    decode_kwargs: dict[str, object] = {}
    if dify_config.EXTERNAL_APP_CONTEXT_TOKEN_ISSUER:
        decode_kwargs["issuer"] = dify_config.EXTERNAL_APP_CONTEXT_TOKEN_ISSUER
    if dify_config.EXTERNAL_APP_CONTEXT_TOKEN_AUDIENCE:
        decode_kwargs["audience"] = dify_config.EXTERNAL_APP_CONTEXT_TOKEN_AUDIENCE

    try:
        decoded = jwt.decode(
            context_token,
            key=token_secret,
            algorithms=["HS256"],
            leeway=dify_config.EXTERNAL_APP_CONTEXT_TOKEN_LEEWAY_SECONDS,
            options={"require": ["exp"]},
            **decode_kwargs,
        )
    except ExpiredSignatureError as ex:
        raise ToolInvokeError("context_token has expired.") from ex
    except InvalidSignatureError as ex:
        raise ToolInvokeError("context_token signature is invalid.") from ex
    except (DecodeError, InvalidTokenError) as ex:
        raise ToolInvokeError("context_token is invalid.") from ex

    if not isinstance(decoded, Mapping):
        raise ToolInvokeError("context_token payload must be an object.")

    context = dict(decoded)
    token_tenant_id = context.get("tenant_id")
    if isinstance(token_tenant_id, str) and token_tenant_id and token_tenant_id != tenant_id:
        raise ToolInvokeError("context_token tenant_id does not match current workspace.")

    return context, True, warnings


def resolve_permission(
    *,
    required_permissions: list[str],
    context_capabilities: list[str],
    token_verified: bool,
    call_mode: str = RUNTIME_CALL_MODE_GATEWAY,
) -> tuple[bool, str, list[str]]:
    if call_mode == RUNTIME_CALL_MODE_DIRECT:
        direct_risk_warning = "direct_mode_risk_external_permission_chain"
        if required_permissions and context_capabilities:
            missing = [permission for permission in required_permissions if permission not in set(context_capabilities)]
            if missing:
                return (
                    False,
                    RUNTIME_PERMISSION_USER_SCOPED,
                    [direct_risk_warning, f"missing_capabilities:{','.join(sorted(missing))}"],
                )
            return True, RUNTIME_PERMISSION_USER_SCOPED, [direct_risk_warning]

        return (
            True,
            RUNTIME_PERMISSION_UNVERIFIED,
            [direct_risk_warning, "direct_mode_unverified_authorization_context"],
        )

    if not required_permissions:
        return True, RUNTIME_PERMISSION_TENANT_SCOPED, []

    if context_capabilities:
        missing = [permission for permission in required_permissions if permission not in set(context_capabilities)]
        if missing:
            return False, RUNTIME_PERMISSION_USER_SCOPED, [f"missing_capabilities:{','.join(sorted(missing))}"]
        return True, RUNTIME_PERMISSION_USER_SCOPED, []

    if token_verified:
        return False, RUNTIME_PERMISSION_USER_SCOPED, ["capabilities_missing_in_context_token"]

    return True, RUNTIME_PERMISSION_TENANT_SCOPED, ["tenant_scoped_fallback_without_verified_token"]


def _tokenize_routing_query(query: str) -> list[str]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    cjk_pattern = re.compile(r"[\u3400-\u9fff]+")
    tokens: list[str] = []
    for token in re.split(r"[\s,.;|?/，。；！？、]+", normalized_query):
        normalized_token = token.strip()
        if normalized_token and normalized_token not in tokens:
            tokens.append(normalized_token)

            # For CJK queries, add bi-character chunks as extra routing hints.
            # Example: "查询项目列表" -> "查询", "项目", "列表".
            for cjk_segment in cjk_pattern.findall(normalized_token):
                if len(cjk_segment) < 2:
                    continue
                for index in range(0, len(cjk_segment) - 1, 2):
                    chunk = cjk_segment[index : index + 2]
                    if len(chunk) == 2 and chunk not in tokens:
                        tokens.append(chunk)
    return tokens


def _build_routing_score(
    *,
    query_tokens: list[str],
    app: TenantExternalApp,
    api: TenantExternalAppApi,
) -> tuple[int, list[str]]:
    if not query_tokens:
        return 0, []

    app_name = app.name.lower()
    app_purpose = (app.app_purpose or "").lower()
    api_name = api.name.lower()
    api_purpose = (api.api_purpose or "").lower()
    api_summary = (api.summary or "").lower()
    api_path = api.path.lower()

    score = 0
    reasons: list[str] = []
    for token in query_tokens:
        if token in app_name:
            score += 120
            reasons.append(f"app_name:{token}")
        if token in app_purpose:
            score += 80
            reasons.append(f"app_purpose:{token}")
        if token in api_name:
            score += 40
            reasons.append(f"api_name:{token}")
        if token in api_purpose:
            score += 30
            reasons.append(f"api_purpose:{token}")
        if token in api_summary:
            score += 20
            reasons.append(f"api_summary:{token}")
        if token in api_path:
            score += 10
            reasons.append(f"api_path:{token}")

    return score, reasons[:6]


def _serialize_runtime_api(
    *,
    app: TenantExternalApp,
    api: TenantExternalAppApi,
    allowed: bool,
    permission_level: str,
    call_mode: str,
    routing_score: int,
    routing_reason: list[str],
    warnings: list[str],
    auth_mode: str,
    auth_ready: bool,
    auth_missing_fields: list[str],
    invoke_hint: dict[str, object],
    routing_priority: int,
    rerank_score: int,
    model_rerank_score: float | None = None,
    final_rerank_score: int | None = None,
) -> dict[str, object]:
    resolved_final_rerank_score = rerank_score if final_rerank_score is None else final_rerank_score
    return {
        "app_id": app.id,
        "app_name": app.name,
        "app_purpose": app.app_purpose,
        "api_id": api.id,
        "api_name": api.name,
        "http_method": api.http_method,
        "path": api.path,
        "summary": api.summary,
        "description": api.description,
        "api_purpose": api.api_purpose,
        "required_permissions": api.required_permissions,
        "allowed": allowed,
        "permission_level": permission_level,
        "call_mode": call_mode,
        "routing_score": routing_score,
        "routing_priority": routing_priority,
        "rerank_score": rerank_score,
        "model_rerank_score": model_rerank_score,
        "final_rerank_score": resolved_final_rerank_score,
        "routing_reason": routing_reason,
        "warnings": warnings,
        "auth_mode": auth_mode,
        "auth_ready": auth_ready,
        "auth_missing_fields": auth_missing_fields,
        "invokable": allowed and auth_ready,
        "invoke_hint": invoke_hint,
    }


def _extract_app_auth_mode(app: TenantExternalApp) -> str:
    raw_auth_mode = getattr(app, "auth_mode", None)
    if hasattr(raw_auth_mode, "value") and isinstance(raw_auth_mode.value, str):  # type: ignore[union-attr]
        return str(raw_auth_mode.value).strip() or "none"
    if isinstance(raw_auth_mode, str) and raw_auth_mode.strip():
        return raw_auth_mode.strip()
    return "none"


def _extract_routing_priority(api: TenantExternalAppApi) -> int:
    request_schema = getattr(api, "request_schema", {})
    if isinstance(request_schema, Mapping):
        raw_priority = request_schema.get("routing_priority")
        if isinstance(raw_priority, (int, float)) and not isinstance(raw_priority, bool):
            return max(-100, min(100, int(raw_priority)))
        if isinstance(raw_priority, str):
            stripped = raw_priority.strip()
            if stripped:
                try:
                    return max(-100, min(100, int(stripped)))
                except ValueError:
                    pass

    text = f"{getattr(api, 'api_purpose', '') or ''} {getattr(api, 'summary', '') or ''}".lower()
    high_priority_hints = ("优先级高", "高优先级", "high priority", "p1")
    low_priority_hints = ("优先级较低", "优先级低", "低优先级", "low priority", "p3")
    if any(hint in text for hint in high_priority_hints):
        return 30
    if any(hint in text for hint in low_priority_hints):
        return -30
    return 0


def _build_model_rerank_document(runtime_api: Mapping[str, object]) -> str:
    sections = [
        f"app_name: {runtime_api.get('app_name', '')}",
        f"app_purpose: {runtime_api.get('app_purpose', '')}",
        f"api_name: {runtime_api.get('api_name', '')}",
        f"http_method: {runtime_api.get('http_method', '')}",
        f"path: {runtime_api.get('path', '')}",
        f"api_purpose: {runtime_api.get('api_purpose', '')}",
        f"summary: {runtime_api.get('summary', '')}",
        f"description: {runtime_api.get('description', '')}",
    ]
    return "\n".join(section for section in sections if section.split(":", 1)[1].strip())


def _initialize_model_rerank_fields(runtime_apis: list[dict[str, object]]) -> None:
    for item in runtime_apis:
        base_score = int(item.get("rerank_score", 0))
        item["model_rerank_score"] = None
        item["final_rerank_score"] = base_score


def _apply_model_rerank(
    *,
    tenant_id: str,
    query_text: str,
    runtime_apis: list[dict[str, object]],
) -> tuple[bool, str | None]:
    _initialize_model_rerank_fields(runtime_apis)

    if not dify_config.EXTERNAL_APP_ROUTING_MODEL_RERANK_ENABLED:
        return False, None
    if not query_text.strip() or len(runtime_apis) <= 1:
        return False, None
    min_candidates = int(dify_config.EXTERNAL_APP_ROUTING_MODEL_RERANK_MIN_CANDIDATES)
    if len(runtime_apis) < max(2, min_candidates):
        return False, None

    candidate_limit = max(1, min(int(dify_config.EXTERNAL_APP_ROUTING_MODEL_RERANK_TOP_K), len(runtime_apis)))
    ranked_indexes = sorted(
        range(len(runtime_apis)),
        key=lambda index: (
            -int(runtime_apis[index].get("rerank_score", 0)),
            -int(runtime_apis[index].get("routing_priority", 0)),
            -int(runtime_apis[index].get("routing_score", 0)),
        ),
    )
    selected_indexes = ranked_indexes[:candidate_limit]
    docs = [_build_model_rerank_document(runtime_apis[index]) for index in selected_indexes]

    try:
        model_manager = ModelManager.for_tenant(tenant_id=tenant_id)
        rerank_model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.RERANK,
        )
        rerank_result = rerank_model_instance.invoke_rerank(query=query_text, docs=docs, top_n=len(docs))
    except Exception as ex:
        logger.warning("external_app_runtime model rerank skipped tenant_id=%s error=%s", tenant_id, ex)
        return False, str(ex)

    score_multiplier = float(dify_config.EXTERNAL_APP_ROUTING_MODEL_RERANK_WEIGHT)
    for rerank_doc in rerank_result.docs:
        model_doc_index = int(getattr(rerank_doc, "index", -1))
        if model_doc_index < 0 or model_doc_index >= len(selected_indexes):
            continue
        runtime_api_index = selected_indexes[model_doc_index]
        model_score = float(getattr(rerank_doc, "score", 0.0))
        model_bonus = int(round(model_score * score_multiplier))
        base_score = int(runtime_apis[runtime_api_index].get("rerank_score", 0))
        runtime_apis[runtime_api_index]["model_rerank_score"] = model_score
        runtime_apis[runtime_api_index]["final_rerank_score"] = base_score + model_bonus

    return True, None


def _assess_auth_readiness(*, app: TenantExternalApp, has_context_token: bool) -> tuple[bool, list[str]]:
    auth_mode = _extract_app_auth_mode(app)
    missing_fields: list[str] = []

    if auth_mode == "none":
        return True, missing_fields

    if auth_mode == "static_bearer":
        token = _extract_static_bearer_token_from_auth_config(app=app)
        if not token and not has_context_token:
            missing_fields.append("auth_config.token_or_context_token")
        return len(missing_fields) == 0, missing_fields

    if auth_mode == "oauth2_client_credentials":
        for field in ("token_url", "client_id", "client_secret"):
            if not _extract_auth_config_string(app=app, key=field):
                missing_fields.append(f"auth_config.{field}")
        return len(missing_fields) == 0, missing_fields

    if auth_mode == "oauth2_authorization_code":
        access_token = _extract_auth_config_string(app=app, key="access_token")
        refresh_required_fields = ("refresh_token", "token_url", "client_id", "client_secret")
        if access_token:
            return True, missing_fields
        for field in refresh_required_fields:
            if not _extract_auth_config_string(app=app, key=field):
                missing_fields.append(f"auth_config.{field}")
        return len(missing_fields) == 0, missing_fields

    return True, missing_fields


def _build_invoke_hint(
    *,
    app: TenantExternalApp,
    api_item: TenantExternalAppApi,
    has_context_token: bool,
) -> dict[str, object]:
    request_schema = getattr(api_item, "request_schema", {})
    required_by_section = _extract_required_params_from_request_schema(request_schema)
    required_by_section["path"].update(_extract_path_placeholders(api_item.path))

    params_template = _build_params_template_from_request_schema(
        request_schema=request_schema,
        required_by_section=required_by_section,
    )
    missing_required_params: list[str] = []
    for section in REQUEST_PARAM_SECTIONS:
        section_params = params_template.get(section, {})
        normalized_section_params = section_params if isinstance(section_params, dict) else {}
        for name in sorted(required_by_section[section]):
            if _is_missing_required_value(
                normalized_section_params,
                name,
                allow_nested_lookup=section == "body",
            ):
                missing_required_params.append(f"{section}.{name}")

    method = str(getattr(api_item, "http_method", "GET")).upper()
    suggested_dry_run = method not in {"GET", "HEAD", "OPTIONS"}

    hint: dict[str, object] = {
        "tool": "invoke_api",
        "required_arguments": ["app_id", "api_id"],
        "suggested_arguments": {
            "app_id": app.id,
            "api_id": api_item.id,
            "params": params_template,
            "dry_run": suggested_dry_run,
        },
        "missing_required_params": missing_required_params,
        "requires_user_input": bool(missing_required_params),
        "requires_context_token": bool(dify_config.EXTERNAL_APP_CONTEXT_TOKEN_REQUIRED),
        "reuse_context_token_from_list_input": has_context_token,
    }
    return hint


def list_available_apis(
    *,
    tenant_id: str,
    query: str | None,
    context_token: str | None,
    max_results: int,
    only_allowed: bool,
) -> dict[str, object]:
    ensure_gateway_enabled()

    bounded_max_results = max(1, min(int(max_results), 1000))
    runtime_context, token_verified, context_warnings = parse_runtime_context(
        tenant_id=tenant_id,
        context_token=context_token,
    )
    capabilities = extract_string_list(runtime_context.get("capabilities"))
    has_context_token = isinstance(context_token, str) and bool(context_token.strip())
    context_token_status = "verified" if token_verified else "not_provided"
    if has_context_token and not token_verified:
        if "context_token_not_verified_missing_secret" in context_warnings:
            context_token_status = "provided_not_verified_missing_secret"
        else:
            context_token_status = "provided_not_verified"

    apps = list(
        db.session.scalars(
            select(TenantExternalApp)
            .where(TenantExternalApp.tenant_id == tenant_id, TenantExternalApp.is_enabled.is_(True))
            .order_by(TenantExternalApp.created_at.desc(), TenantExternalApp.id.desc())
        ).all()
    )
    if not apps:
        return {
            "apis": [],
            "summary": {
                "total": 0,
                "token_verified": token_verified,
                "context_token_provided": has_context_token,
                "context_token_status": context_token_status,
                "context_token_warnings": context_warnings,
                "routing_strategy": "app_first_v1",
                "model_rerank_enabled": bool(dify_config.EXTERNAL_APP_ROUTING_MODEL_RERANK_ENABLED),
                "model_rerank_applied": False,
                "model_rerank_error": None,
                "next_action": None,
            },
        }

    app_by_id = {app.id: app for app in apps}
    api_items = list(
        db.session.scalars(
            select(TenantExternalAppApi)
            .where(
                TenantExternalAppApi.tenant_id == tenant_id,
                TenantExternalAppApi.app_id.in_([app.id for app in apps]),
                TenantExternalAppApi.is_enabled.is_(True),
            )
            .order_by(
                TenantExternalAppApi.http_method.asc(),
                TenantExternalAppApi.path.asc(),
                TenantExternalAppApi.id.asc(),
            )
        ).all()
    )

    query_text = query.strip() if isinstance(query, str) else ""
    normalized_query = query_text.lower() if query_text else None
    routing_tokens = _tokenize_routing_query(query_text)
    runtime_apis: list[dict[str, object]] = []
    auth_unready_count = 0
    permission_denied_count = 0

    for api_item in api_items:
        app = app_by_id.get(api_item.app_id)
        if app is None:
            continue

        if normalized_query:
            search_index = " ".join(
                value
                for value in [
                    app.name,
                    app.app_purpose or "",
                    api_item.name,
                    api_item.http_method,
                    api_item.path,
                    api_item.summary or "",
                    api_item.api_purpose or "",
                ]
                if isinstance(value, str)
            ).lower()
            if routing_tokens:
                if not any(token in search_index for token in routing_tokens):
                    continue
            elif normalized_query not in search_index:
                continue

        call_mode = extract_call_mode_from_auth_config(app.auth_config)
        required_permissions = extract_string_list(api_item.required_permissions)
        allowed, permission_level, permission_warnings = resolve_permission(
            required_permissions=required_permissions,
            context_capabilities=capabilities,
            token_verified=token_verified,
            call_mode=call_mode,
        )
        if not allowed:
            permission_denied_count += 1

        auth_mode = _extract_app_auth_mode(app)
        auth_ready, auth_missing_fields = _assess_auth_readiness(app=app, has_context_token=has_context_token)
        if not auth_ready:
            auth_unready_count += 1

        if only_allowed and (not allowed or not auth_ready):
            continue

        routing_score, routing_reason = _build_routing_score(query_tokens=routing_tokens, app=app, api=api_item)
        routing_priority = _extract_routing_priority(api_item)
        rerank_score = routing_score + routing_priority
        invoke_hint = _build_invoke_hint(app=app, api_item=api_item, has_context_token=has_context_token)
        runtime_apis.append(
            _serialize_runtime_api(
                app=app,
                api=api_item,
                allowed=allowed,
                permission_level=permission_level,
                call_mode=call_mode,
                routing_score=routing_score,
                routing_reason=routing_reason,
                warnings=context_warnings + permission_warnings,
                auth_mode=auth_mode,
                auth_ready=auth_ready,
                auth_missing_fields=auth_missing_fields,
                invoke_hint=invoke_hint,
                routing_priority=routing_priority,
                rerank_score=rerank_score,
            )
        )
        if len(runtime_apis) >= bounded_max_results:
            break

    model_rerank_applied, model_rerank_error = _apply_model_rerank(
        tenant_id=tenant_id,
        query_text=query_text,
        runtime_apis=runtime_apis,
    )

    if routing_tokens:
        runtime_apis.sort(
            key=lambda item: (
                -int(item.get("final_rerank_score", item.get("rerank_score", 0))),
                -int(item.get("routing_priority", 0)),
                -int(item.get("routing_score", 0)),
                str(item.get("app_name", "")),
                str(item.get("api_name", "")),
            )
        )

    next_action = runtime_apis[0].get("invoke_hint") if runtime_apis else None
    routing_strategy = "app_first_v2_rule_model_rerank" if model_rerank_applied else "app_first_v1"

    return {
        "apis": runtime_apis,
        "summary": {
            "total": len(runtime_apis),
            "token_verified": token_verified,
            "context_token_provided": has_context_token,
            "context_token_status": context_token_status,
            "context_token_warnings": context_warnings,
            "routing_strategy": routing_strategy,
            "permission_denied_count": permission_denied_count,
            "auth_unready_count": auth_unready_count,
            "model_rerank_enabled": bool(dify_config.EXTERNAL_APP_ROUTING_MODEL_RERANK_ENABLED),
            "model_rerank_applied": model_rerank_applied,
            "model_rerank_error": model_rerank_error,
            "next_action": next_action,
        },
    }


def _extract_required_params_from_request_schema(request_schema: object) -> dict[str, set[str]]:
    required_by_section: dict[str, set[str]] = {
        "path": set(),
        "query": set(),
        "body": set(),
        "headers": set(),
    }
    if not isinstance(request_schema, Mapping):
        return required_by_section

    for section in REQUEST_PARAM_SECTIONS:
        section_items = request_schema.get(section)
        if not isinstance(section_items, list):
            continue
        for item in section_items:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            normalized_name = name.strip()
            if not normalized_name:
                continue
            if bool(item.get("required")):
                required_by_section[section].add(normalized_name)

    invoke_constraints = request_schema.get("invoke_constraints")
    if isinstance(invoke_constraints, Mapping):
        for required_key in ("required_fields", "required"):
            required_mapping = invoke_constraints.get(required_key)
            if not isinstance(required_mapping, Mapping):
                continue
            for raw_section, raw_names in required_mapping.items():
                if not isinstance(raw_section, str):
                    continue
                section = raw_section.strip().lower()
                if section not in required_by_section or not isinstance(raw_names, list):
                    continue
                for raw_name in raw_names:
                    if not isinstance(raw_name, str):
                        continue
                    normalized_name = raw_name.strip()
                    if normalized_name:
                        required_by_section[section].add(normalized_name)

    return required_by_section


def _extract_path_placeholders(path_template: str) -> set[str]:
    return {
        match.strip()
        for match in re.findall(r"\{([^{}]+)\}", path_template)
        if isinstance(match, str) and match.strip()
    }


def _normalize_template_value(raw_value: object) -> object:
    if not isinstance(raw_value, str):
        return raw_value

    normalized = raw_value.strip()
    if not normalized:
        return ""

    if normalized[0] in {'{', '[', '"'} or normalized.lower() in {"true", "false", "null"}:
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return normalized
    return normalized


def _extract_params_template_from_items(section_items: object) -> dict[str, object]:
    if not isinstance(section_items, list):
        return {}

    template: dict[str, object] = {}
    for item in section_items:
        if not isinstance(item, Mapping):
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if not name:
            continue

        if "example" in item:
            template[name] = _normalize_template_value(item.get("example"))
            continue
        if "default" in item:
            template[name] = _normalize_template_value(item.get("default"))
            continue

        raw_type = item.get("type")
        normalized_type = raw_type.strip().lower() if isinstance(raw_type, str) else "string"
        if normalized_type == "object":
            template[name] = {}
        elif normalized_type == "array":
            template[name] = []
        elif normalized_type == "boolean":
            template[name] = False
        elif normalized_type in {"number", "integer"}:
            template[name] = 0
        else:
            template[name] = ""

    return template


def _merge_explicit_params_template(*, template_by_section: dict[str, dict[str, object]], raw_template: object) -> None:
    if not isinstance(raw_template, Mapping):
        return

    for section in REQUEST_PARAM_SECTIONS:
        raw_section_template = raw_template.get(section)
        if not isinstance(raw_section_template, Mapping):
            continue
        for raw_name, raw_value in raw_section_template.items():
            if not isinstance(raw_name, str):
                continue
            normalized_name = raw_name.strip()
            if not normalized_name:
                continue
            template_by_section[section][normalized_name] = raw_value


def _build_params_template_from_request_schema(
    *,
    request_schema: object,
    required_by_section: dict[str, set[str]],
) -> dict[str, dict[str, object]]:
    params_template: dict[str, dict[str, object]] = {section: {} for section in REQUEST_PARAM_SECTIONS}
    if isinstance(request_schema, Mapping):
        for section in REQUEST_PARAM_SECTIONS:
            params_template[section].update(_extract_params_template_from_items(request_schema.get(section)))

        _merge_explicit_params_template(
            template_by_section=params_template,
            raw_template=request_schema.get("fixed_params_template"),
        )

        invoke_constraints = request_schema.get("invoke_constraints")
        if isinstance(invoke_constraints, Mapping):
            _merge_explicit_params_template(
                template_by_section=params_template,
                raw_template=invoke_constraints.get("params_template"),
            )
            body_template = invoke_constraints.get("body_template")
            if isinstance(body_template, Mapping):
                params_template["body"] = {
                    str(key).strip(): value
                    for key, value in body_template.items()
                    if isinstance(key, str) and key.strip()
                }

    for section in REQUEST_PARAM_SECTIONS:
        for name in sorted(required_by_section[section]):
            params_template[section].setdefault(name, "")

    return params_template


def _normalize_mapping_keys(raw_mapping: Mapping[object, object]) -> dict[str, object]:
    normalized_mapping: dict[str, object] = {}
    for raw_key, raw_value in raw_mapping.items():
        if not isinstance(raw_key, str):
            continue
        normalized_key = raw_key.strip()
        if not normalized_key:
            continue
        normalized_mapping[normalized_key] = raw_value
    return normalized_mapping


def _parse_section_params_mapping(value: object) -> dict[str, object] | None:
    if isinstance(value, Mapping):
        return _normalize_mapping_keys(value)

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return {}

    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, Mapping):
        return _normalize_mapping_keys(parsed)

    if "=" in normalized and not normalized.startswith(("{", "[")):
        query_pairs = parse_qsl(normalized.lstrip("?"), keep_blank_values=True)
        if query_pairs:
            return {key.strip(): item for key, item in query_pairs if key.strip()}

    return None


def _build_section_key_hints(
    *,
    required_by_section: dict[str, set[str]],
    params_template: dict[str, dict[str, object]],
) -> dict[str, set[str]]:
    hints: dict[str, set[str]] = {section: set() for section in REQUEST_PARAM_SECTIONS}
    for section in REQUEST_PARAM_SECTIONS:
        hints[section].update(params_template.get(section, {}).keys())
        for raw_name in required_by_section[section]:
            normalized_name = raw_name.strip()
            if not normalized_name:
                continue
            hints[section].add(normalized_name.split(".", 1)[0])
    return hints


def _infer_flat_param_target_section(
    *,
    param_name: str,
    section_key_hints: dict[str, set[str]],
    default_section: str,
) -> str:
    lowered_name = param_name.lower()
    if lowered_name in {"authorization", "content-type", "accept", "cookie"} or lowered_name.startswith("x-"):
        return "headers"

    candidate_sections = [section for section in REQUEST_PARAM_SECTIONS if param_name in section_key_hints[section]]
    if len(candidate_sections) == 1:
        return candidate_sections[0]

    return default_section


def _merge_invoke_params_with_schema_template(
    *,
    request_schema: object,
    api_path: str,
    api_method: str,
    params: dict[str, object],
) -> dict[str, object]:
    required_by_section = _extract_required_params_from_request_schema(request_schema)
    required_by_section["path"].update(_extract_path_placeholders(api_path))
    params_template = _build_params_template_from_request_schema(
        request_schema=request_schema,
        required_by_section=required_by_section,
    )

    merged_params: dict[str, object] = dict(params)
    explicit_section_keys: dict[str, set[str]] = {section: set() for section in REQUEST_PARAM_SECTIONS}
    for section in REQUEST_PARAM_SECTIONS:
        section_template = dict(params_template.get(section, {}))
        raw_section_params = params.get(section)
        parsed_section_params = _parse_section_params_mapping(raw_section_params)
        if parsed_section_params is not None:
            explicit_section_keys[section].update(parsed_section_params.keys())
            section_template.update(parsed_section_params)
            merged_params[section] = section_template
            continue

        if raw_section_params is None:
            if section_template:
                merged_params[section] = section_template
            continue

        merged_params[section] = raw_section_params

    flat_params: dict[str, object] = {
        normalized_key: value
        for key, value in params.items()
        if isinstance(key, str)
        and (normalized_key := key.strip())
        and normalized_key not in REQUEST_PARAM_SECTIONS
    }
    if flat_params:
        section_key_hints = _build_section_key_hints(
            required_by_section=required_by_section,
            params_template=params_template,
        )
        default_section = "query" if api_method.upper() in {"GET", "HEAD", "OPTIONS"} else "body"

        for section in REQUEST_PARAM_SECTIONS:
            existing_section = merged_params.get(section)
            if not isinstance(existing_section, dict):
                existing_section = {}

            target_pairs = {
                name: value
                for name, value in flat_params.items()
                if _infer_flat_param_target_section(
                    param_name=name,
                    section_key_hints=section_key_hints,
                    default_section=default_section,
                )
                == section
            }
            for name, value in target_pairs.items():
                if name in explicit_section_keys[section]:
                    continue
                existing_section[name] = value
            if existing_section:
                merged_params[section] = existing_section

    return merged_params


def _lookup_nested_mapping_value(params_container: Mapping[str, object], path: str) -> object:
    current: object = params_container
    for segment in path.split("."):
        normalized_segment = segment.strip()
        if not normalized_segment:
            return None
        if not isinstance(current, Mapping) or normalized_segment not in current:
            return None
        current = current.get(normalized_segment)
    return current


def _is_missing_required_value(
    params_container: dict[str, object],
    name: str,
    *,
    allow_nested_lookup: bool = False,
) -> bool:
    if allow_nested_lookup and "." in name:
        value = _lookup_nested_mapping_value(params_container, name)
        if value is None:
            return True
    else:
        if name not in params_container:
            return True
        value = params_container.get(name)

    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _validate_required_invoke_params(*, api_item: TenantExternalAppApi, params: dict[str, object]) -> None:
    path_params = params.get("path")
    query_params = params.get("query")
    body_params = params.get("body")
    headers_params = params.get("headers")

    normalized_path_params = path_params if isinstance(path_params, dict) else {}
    normalized_query_params = query_params if isinstance(query_params, dict) else {}
    normalized_body_params = body_params if isinstance(body_params, dict) else {}
    normalized_headers_params = headers_params if isinstance(headers_params, dict) else {}

    required_by_section = _extract_required_params_from_request_schema(getattr(api_item, "request_schema", {}))
    required_by_section["path"].update(_extract_path_placeholders(api_item.path))

    missing_params: list[str] = []
    for name in sorted(required_by_section["path"]):
        if _is_missing_required_value(normalized_path_params, name, allow_nested_lookup=False):
            missing_params.append(f"path.{name}")
    for name in sorted(required_by_section["query"]):
        if _is_missing_required_value(normalized_query_params, name, allow_nested_lookup=False):
            missing_params.append(f"query.{name}")
    for name in sorted(required_by_section["body"]):
        if _is_missing_required_value(normalized_body_params, name, allow_nested_lookup=True):
            missing_params.append(f"body.{name}")
    for name in sorted(required_by_section["headers"]):
        if _is_missing_required_value(normalized_headers_params, name, allow_nested_lookup=False):
            missing_params.append(f"headers.{name}")

    if missing_params:
        raise ToolInvokeError(f"Missing required parameters: {', '.join(missing_params)}.")


def _render_path(path_template: str, path_params: dict[str, object]) -> str:
    rendered = path_template
    for key, value in path_params.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def _normalize_optional_base_url(*, raw_value: object, field_name: str) -> str | None:
    if not isinstance(raw_value, str):
        return None

    normalized = raw_value.strip()
    if not normalized:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ToolInvokeError(f"{field_name} must start with http:// or https://.")
    return normalized


def _extract_api_base_url_override(api_item: TenantExternalAppApi) -> str | None:
    request_schema = getattr(api_item, "request_schema", {})
    if not isinstance(request_schema, Mapping):
        return None
    return _normalize_optional_base_url(
        raw_value=request_schema.get("base_url_override"),
        field_name="request_schema.base_url_override",
    )


def _build_invoke_target_url(
    *,
    app: TenantExternalApp,
    api_item: TenantExternalAppApi,
    params: dict[str, object],
) -> str:
    raw_base_url = _extract_api_base_url_override(api_item) or _normalize_optional_base_url(
        raw_value=app.auth_config.get("base_url"),
        field_name="auth_config.base_url",
    )
    if not raw_base_url:
        raise ToolInvokeError("auth_config.base_url is required for runtime invoke.")

    path_params = params.get("path")
    normalized_path_params = path_params if isinstance(path_params, dict) else {}
    rendered_path = _render_path(api_item.path, normalized_path_params)
    return f"{raw_base_url.rstrip('/')}{rendered_path}"


def _extract_auth_config_string(*, app: TenantExternalApp, key: str) -> str | None:
    raw_value = app.auth_config.get(key)
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def _extract_static_bearer_token_from_auth_config(*, app: TenantExternalApp) -> str | None:
    for key in ("token", "token_or_context_token", "context_token", "access_token", "authorization", "Authorization"):
        token = _extract_auth_config_string(app=app, key=key)
        if token:
            return token

    headers_mapping = _extract_auth_config_str_dict(app=app, key="headers")
    for header_key in ("Authorization", "authorization"):
        raw_token = headers_mapping.get(header_key)
        if isinstance(raw_token, str):
            normalized = raw_token.strip()
            if normalized:
                return normalized

    return None


def _normalize_bearer_token_value(token: str) -> str:
    normalized = token.strip()
    if not normalized:
        return ""
    if normalized.lower().startswith("bearer"):
        normalized = re.sub(r"^bearer[\s:]+", "", normalized, flags=re.IGNORECASE).strip()

    # Prefer extracting a JWT-like token segment when the input contains
    # additional natural language text.
    jwt_match = re.search(r"([A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})", normalized)
    if jwt_match:
        return jwt_match.group(1)

    # Fallback: pick the first plausible bearer token chunk.
    for raw_chunk in re.split(r"[\s,;，；]+", normalized):
        chunk = raw_chunk.strip().strip("'\"`")
        if not chunk:
            continue
        if "=" in chunk and chunk.lower().startswith(("token=", "authorization=", "bearer=")):
            chunk = chunk.split("=", 1)[1].strip().strip("'\"`")
        if not chunk:
            continue
        if (
            len(chunk) >= 12
            and re.fullmatch(r"[A-Za-z0-9\-._~+/]+=*", chunk)
            and re.search(r"[0-9._~+/=-]", chunk)
        ):
            return chunk
    return normalized


def _is_expired_jwt_bearer_token(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded_payload = base64.urlsafe_b64decode(f"{payload_segment}{padding}")
        payload = json.loads(decoded_payload)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False

    if not isinstance(payload, Mapping):
        return False

    expires_at = payload.get("exp")
    if not isinstance(expires_at, (int, float)):
        return False

    return float(expires_at) <= time.time()


def _decode_invoke_response_payload(response: object) -> object:
    if not isinstance(getattr(response, "headers", None), Mapping):
        return getattr(response, "text", "")

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        try:
            return response.json()
        except json.JSONDecodeError:
            return response.text
    return response.text


def _is_auth_failure_response(
    *,
    status_code: int | None,
    business_code: int | str | None,
    business_message: str | None,
    response_payload: object,
) -> bool:
    if isinstance(status_code, int) and status_code == 401:
        return True

    normalized_business_code = str(business_code).strip() if business_code is not None else ""
    if normalized_business_code == "401":
        return True

    text_candidates: list[str] = []
    if isinstance(business_message, str) and business_message.strip():
        text_candidates.append(business_message.strip().lower())
    if isinstance(response_payload, str) and response_payload.strip():
        text_candidates.append(response_payload.strip().lower())

    auth_failure_markers = (
        "登录状态已过期",
        "认证已过期",
        "认证过期",
        "token expired",
        "access token expired",
        "unauthorized",
        "invalid token",
        "login expired",
    )
    return any(marker.lower() in text for marker in auth_failure_markers for text in text_candidates)


def _extract_auth_config_str_dict(*, app: TenantExternalApp, key: str) -> dict[str, str]:
    raw_value = app.auth_config.get(key)
    if not isinstance(raw_value, Mapping):
        return {}
    result: dict[str, str] = {}
    for raw_key, raw_item in raw_value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_item, str):
            continue
        normalized_key = raw_key.strip()
        normalized_item = raw_item.strip()
        if not normalized_key or not normalized_item:
            continue
        result[normalized_key] = normalized_item
    return result


def _extract_oauth_access_token_from_response(response: object) -> tuple[str, str, int | None]:
    if not hasattr(response, "status_code"):
        raise ToolInvokeError("OAuth adapter received invalid token response.")

    status_code = int(response.status_code)  # type: ignore[attr-defined]
    if status_code >= 400:
        raise ToolInvokeError(f"OAuth token endpoint failed with status {status_code}.")

    response_json_getter = getattr(response, "json", None)
    if not callable(response_json_getter):
        raise ToolInvokeError("OAuth token endpoint returned non-JSON payload.")

    try:
        payload = response_json_getter()
    except Exception as ex:
        raise ToolInvokeError("OAuth token endpoint returned invalid JSON payload.") from ex

    if not isinstance(payload, Mapping):
        raise ToolInvokeError("OAuth token endpoint payload must be an object.")

    raw_access_token = payload.get("access_token")
    if not isinstance(raw_access_token, str) or not raw_access_token.strip():
        raise ToolInvokeError("OAuth token endpoint missing access_token.")
    token = raw_access_token.strip()

    raw_token_type = payload.get("token_type")
    token_type = raw_token_type.strip() if isinstance(raw_token_type, str) and raw_token_type.strip() else "Bearer"

    expires_in_value: int | None = None
    raw_expires_in = payload.get("expires_in")
    if isinstance(raw_expires_in, (int, float)):
        expires_in_value = int(raw_expires_in)

    return token, token_type, expires_in_value


def _fetch_oauth2_client_credentials_token(*, app: TenantExternalApp, timeout_seconds: float) -> tuple[str, str]:
    token_url = _extract_auth_config_string(app=app, key="token_url")
    client_id = _extract_auth_config_string(app=app, key="client_id")
    client_secret = _extract_auth_config_string(app=app, key="client_secret")
    if not token_url or not client_id or not client_secret:
        raise ToolInvokeError("oauth2_client_credentials requires token_url/client_id/client_secret in auth_config.")

    token_auth_method = _extract_auth_config_string(app=app, key="token_auth_method") or "client_secret_post"
    token_headers = _extract_auth_config_str_dict(app=app, key="token_headers")
    token_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    payload: dict[str, str] = {"grant_type": "client_credentials"}
    scope = _extract_auth_config_string(app=app, key="scope")
    audience = _extract_auth_config_string(app=app, key="audience")
    if scope:
        payload["scope"] = scope
    if audience:
        payload["audience"] = audience

    if token_auth_method == "client_secret_basic":
        basic_token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        token_headers["Authorization"] = f"Basic {basic_token}"
    else:
        payload["client_id"] = client_id
        payload["client_secret"] = client_secret

    try:
        response = ssrf_proxy.post(
            url=token_url,
            headers=token_headers,
            data=payload,
            timeout=timeout_seconds,
            max_retries=0,
        )
    except Exception as ex:
        logger.exception("oauth2_client_credentials token fetch failed app_id=%s", app.id)
        raise ToolInvokeError("Failed to fetch OAuth2 client_credentials access token.") from ex

    token, token_type, _ = _extract_oauth_access_token_from_response(response)
    return token, token_type


def _fetch_oauth2_authorization_code_token(*, app: TenantExternalApp, timeout_seconds: float) -> tuple[str, str]:
    access_token = _extract_auth_config_string(app=app, key="access_token")
    token_type = _extract_auth_config_string(app=app, key="token_type") or "Bearer"
    expires_at = app.auth_config.get("expires_at")
    if access_token and (not isinstance(expires_at, (int, float)) or float(expires_at) > time.time()):
        return access_token, token_type

    refresh_token = _extract_auth_config_string(app=app, key="refresh_token")
    token_url = _extract_auth_config_string(app=app, key="token_url")
    client_id = _extract_auth_config_string(app=app, key="client_id")
    client_secret = _extract_auth_config_string(app=app, key="client_secret")
    if not refresh_token or not token_url or not client_id or not client_secret:
        raise ToolInvokeError("oauth2_authorization_code requires valid access_token or refresh credentials.")

    token_headers = _extract_auth_config_str_dict(app=app, key="token_headers")
    token_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    scope = _extract_auth_config_string(app=app, key="scope")
    if scope:
        payload["scope"] = scope

    try:
        response = ssrf_proxy.post(
            url=token_url,
            headers=token_headers,
            data=payload,
            timeout=timeout_seconds,
            max_retries=0,
        )
    except Exception as ex:
        logger.exception("oauth2_authorization_code refresh failed app_id=%s", app.id)
        raise ToolInvokeError("Failed to refresh OAuth2 authorization_code access token.") from ex

    refreshed_token, refreshed_token_type, expires_in = _extract_oauth_access_token_from_response(response)
    updated_auth_config = dict(app.auth_config)
    updated_auth_config["access_token"] = refreshed_token
    updated_auth_config["token_type"] = refreshed_token_type
    if expires_in is not None and expires_in > 0:
        updated_auth_config["expires_at"] = int(time.time()) + expires_in
    response_json = response.json()
    if isinstance(response_json, Mapping) and isinstance(response_json.get("refresh_token"), str):
        updated_refresh_token = str(response_json["refresh_token"]).strip()
        if updated_refresh_token:
            updated_auth_config["refresh_token"] = updated_refresh_token
    app.auth_config = updated_auth_config
    return refreshed_token, refreshed_token_type


def _build_custom_adapter_auth(*, app: TenantExternalApp) -> tuple[dict[str, str], dict[str, str], list[str]]:
    headers = _extract_auth_config_str_dict(app=app, key="headers")
    query_params = _extract_auth_config_str_dict(app=app, key="query")
    warnings: list[str] = []

    adapter_type = _extract_auth_config_string(app=app, key="type")
    if adapter_type == "api_key":
        api_key = _extract_auth_config_string(app=app, key="api_key")
        if not api_key:
            raise ToolInvokeError("custom api_key adapter requires auth_config.api_key.")
        api_key_in = (_extract_auth_config_string(app=app, key="api_key_in") or "header").lower()
        api_key_name = _extract_auth_config_string(app=app, key="api_key_name") or "X-API-Key"
        if api_key_in == "query":
            query_params[api_key_name] = api_key
        else:
            headers[api_key_name] = api_key
        return headers, query_params, warnings

    warnings.append("custom_adapter_without_standard_type")
    return headers, query_params, warnings


def _build_invoke_credential_auth(
    *,
    app: TenantExternalApp,
    timeout_seconds: float,
    context_token: str | None = None,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    auth_mode = app.auth_mode.value
    if auth_mode == "none":
        return {}, {}, []

    if auth_mode == "static_bearer":
        token = _extract_static_bearer_token_from_auth_config(app=app)
        if token:
            normalized_token = _normalize_bearer_token_value(token)
            if not normalized_token:
                return {}, {}, ["static_bearer_missing_token_no_auth_header"]
            if _is_expired_jwt_bearer_token(normalized_token):
                if isinstance(context_token, str) and context_token.strip():
                    normalized_context_token = _normalize_bearer_token_value(context_token)
                    if normalized_context_token:
                        return (
                            {"Authorization": f"Bearer {normalized_context_token}"},
                            {},
                            ["static_bearer_expired_context_token_fallback"],
                        )
            return {"Authorization": f"Bearer {normalized_token}"}, {}, []
        if isinstance(context_token, str) and context_token.strip():
            normalized_context_token = _normalize_bearer_token_value(context_token)
            if normalized_context_token:
                return (
                    {"Authorization": f"Bearer {normalized_context_token}"},
                    {},
                    ["static_bearer_fallback_context_token"],
                )
        return {}, {}, ["static_bearer_missing_token_no_auth_header"]

    if auth_mode == "oauth2_client_credentials":
        token, token_type = _fetch_oauth2_client_credentials_token(app=app, timeout_seconds=timeout_seconds)
        return {"Authorization": f"{token_type} {token}"}, {}, []

    if auth_mode == "oauth2_authorization_code":
        token, token_type = _fetch_oauth2_authorization_code_token(app=app, timeout_seconds=timeout_seconds)
        return {"Authorization": f"{token_type} {token}"}, {}, []

    if auth_mode == "custom":
        return _build_custom_adapter_auth(app=app)

    raise ToolInvokeError(f"Unsupported auth_mode for runtime invoke: {auth_mode}.")


def _invoke_external_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, object],
    json_payload: object,
    timeout_seconds: float,
) -> object:
    requester = getattr(ssrf_proxy, method.lower(), None)
    if not callable(requester):
        raise ToolInvokeError(f"Unsupported runtime invoke method: {method}.")

    return requester(
        url=url,
        headers=headers,
        params=params,
        json=json_payload,
        timeout=timeout_seconds,
        max_retries=0,
    )


def _record_runtime_audit(
    *,
    account_id: str,
    tenant_id: str,
    action: str,
    content: dict[str, object],
    invoke_from: str | None = None,
    created_ip: str = "0.0.0.0",
) -> None:
    normalized_content = dict(content)
    if invoke_from:
        normalized_content["invoke_from"] = invoke_from
    db.session.add(
        OperationLog(
            tenant_id=tenant_id,
            account_id=account_id,
            action=action,
            content=normalized_content,
            created_ip=created_ip,
        )
    )


def _parse_optional_params_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return {}
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as ex:
            raise ToolInvokeError("params must be a JSON object string.") from ex
        if not isinstance(parsed, dict):
            raise ToolInvokeError("params must be a JSON object.")
        return parsed
    raise ToolInvokeError("params must be an object or JSON string.")


def _extract_first_present_field(payload: Mapping[str, object], field_candidates: tuple[str, ...]) -> object:
    for field in field_candidates:
        if field in payload:
            return payload.get(field)
    return None


def _extract_first_non_empty_string(payload: Mapping[str, object], field_candidates: tuple[str, ...]) -> str | None:
    for field in field_candidates:
        raw_value = payload.get(field)
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                return normalized
    return None


def _normalize_business_code(raw_code: object) -> int | str | None:
    if isinstance(raw_code, bool):
        return None
    if isinstance(raw_code, (int, float)):
        return int(raw_code)
    if isinstance(raw_code, str):
        normalized = raw_code.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return int(normalized)
        prefixed_match = re.match(r"^(\d+)\D.*$", normalized)
        if prefixed_match:
            return int(prefixed_match.group(1))
        return normalized
    return None


def _parse_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "ok", "success"}:
            return True
        if normalized in {"false", "0", "no", "fail", "failed", "error"}:
            return False
    return None


def _is_likely_error_message(message: str) -> bool:
    normalized_message = message.strip().lower()
    if not normalized_message:
        return False
    return any(hint in normalized_message for hint in BUSINESS_ERROR_MESSAGE_HINTS)


def _evaluate_business_result(response_payload: object) -> tuple[str, int | str | None, str | None, str | None]:
    if not isinstance(response_payload, Mapping):
        return "unknown", None, None, None

    payload = dict(response_payload)
    raw_code = _extract_first_present_field(
        payload,
        ("code", "status", "biz_code", "bizCode", "business_code", "businessCode", "error_code", "errorCode"),
    )
    business_code = _normalize_business_code(raw_code)
    business_message = _extract_first_non_empty_string(
        payload,
        ("message", "msg", "business_message", "businessMessage", "error_message", "errorMessage", "error", "detail"),
    )

    raw_success = _extract_first_present_field(payload, ("success", "ok", "is_success", "isSuccess", "succeeded"))
    success_flag = _parse_optional_bool(raw_success)

    raw_error_field = _extract_first_present_field(payload, ("error", "err", "error_detail", "errorDetail"))
    has_error_field = False
    if isinstance(raw_error_field, Mapping):
        has_error_field = bool(raw_error_field)
    elif isinstance(raw_error_field, str):
        normalized_error = raw_error_field.strip().lower()
        has_error_field = bool(normalized_error and normalized_error not in {"none", "null", "ok", "success"})

    has_business_signal = any(
        [
            business_code is not None,
            business_message is not None,
            success_flag is not None,
            has_error_field,
        ]
    )
    if not has_business_signal:
        return "unknown", None, None, None

    business_code_failed = False
    if isinstance(business_code, int):
        business_code_failed = business_code not in {0, 200}
    elif isinstance(business_code, str):
        normalized_code = business_code.strip().lower()
        if normalized_code in {"ok", "success", "succeeded", "0", "200"}:
            business_code_failed = False
        elif normalized_code in {"error", "failed", "fail", "false"}:
            business_code_failed = True

    data_is_null = "data" in payload and payload.get("data") is None
    message_failed = bool(
        business_message
        and _is_likely_error_message(business_message)
        and (data_is_null or business_code_failed or success_flag is False or has_error_field)
    )

    is_business_failed = (
        success_flag is False
        or business_code_failed
        or (has_error_field and success_flag is not True)
        or message_failed
    )

    if not is_business_failed:
        return "success", business_code, business_message, None

    if business_message:
        failure_reason = business_message
    elif business_code is not None:
        failure_reason = f"code:{business_code}"
    elif has_error_field:
        failure_reason = "error_field_present"
    else:
        failure_reason = "business_response_failed"

    return "failed", business_code, business_message, failure_reason


def _truncate_optional_text(value: str | None, limit: int = 512) -> str | None:
    if not value:
        return None
    return value if len(value) <= limit else value[:limit]


def invoke_api(
    *,
    tenant_id: str,
    account_id: str,
    app_id: str,
    api_id: str,
    context_token: str | None,
    params: object,
    dry_run: bool,
    timeout_seconds: float | None,
    invoke_from: str | None = None,
    created_ip: str = "0.0.0.0",
) -> dict[str, object]:
    ensure_gateway_enabled()

    runtime_context, token_verified, context_warnings = parse_runtime_context(
        tenant_id=tenant_id,
        context_token=context_token,
    )
    capabilities = extract_string_list(runtime_context.get("capabilities"))

    app = db.session.scalar(
        select(TenantExternalApp)
        .where(
            TenantExternalApp.id == app_id,
            TenantExternalApp.tenant_id == tenant_id,
            TenantExternalApp.is_enabled.is_(True),
        )
        .limit(1)
    )
    if app is None:
        raise ToolInvokeError("External app not found or disabled.")

    api_item = db.session.scalar(
        select(TenantExternalAppApi)
        .where(
            TenantExternalAppApi.id == api_id,
            TenantExternalAppApi.app_id == app.id,
            TenantExternalAppApi.tenant_id == tenant_id,
            TenantExternalAppApi.is_enabled.is_(True),
        )
        .limit(1)
    )
    if api_item is None:
        raise ToolInvokeError("External app api not found or disabled.")

    required_permissions = extract_string_list(api_item.required_permissions)
    call_mode = extract_call_mode_from_auth_config(app.auth_config)
    allowed, permission_level, permission_warnings = resolve_permission(
        required_permissions=required_permissions,
        context_capabilities=capabilities,
        token_verified=token_verified,
        call_mode=call_mode,
    )
    if not allowed:
        raise ToolInvokeError("Current auth context does not satisfy required_permissions.")

    trace_id = str(runtime_context.get("trace_id")) if isinstance(runtime_context.get("trace_id"), str) else uuid4().hex
    warnings = context_warnings + permission_warnings
    normalized_params = _parse_optional_params_object(params)
    normalized_params = _merge_invoke_params_with_schema_template(
        request_schema=getattr(api_item, "request_schema", {}),
        api_path=api_item.path,
        api_method=api_item.http_method,
        params=normalized_params,
    )

    _validate_required_invoke_params(api_item=api_item, params=normalized_params)
    target_url = _build_invoke_target_url(app=app, api_item=api_item, params=normalized_params)

    query = normalized_params.get("query")
    body = normalized_params.get("body")
    payload_headers = normalized_params.get("headers")
    query_params = query if isinstance(query, dict) else {}
    json_body = body if isinstance(body, dict) else body

    timeout_value = float(timeout_seconds) if timeout_seconds else dify_config.EXTERNAL_APP_GATEWAY_INVOKE_TIMEOUT
    adapter_headers, adapter_query_params, adapter_warnings = _build_invoke_credential_auth(
        app=app,
        timeout_seconds=timeout_value,
        context_token=context_token,
    )
    warnings.extend(adapter_warnings)
    headers: dict[str, str] = {}
    if isinstance(payload_headers, dict):
        headers.update({str(k): str(v) for k, v in payload_headers.items()})
    headers.update(adapter_headers)
    normalized_context_token = _normalize_bearer_token_value(context_token) if isinstance(context_token, str) else None
    context_token_authorization = f"Bearer {normalized_context_token}" if normalized_context_token else None

    merged_query_params: dict[str, object] = dict(query_params)
    merged_query_params.update(adapter_query_params)

    if dry_run:
        result_payload = {
            "trace_id": trace_id,
            "permission_level_actual": permission_level,
            "call_mode_actual": call_mode,
            "warnings": warnings,
            "dry_run": True,
            "target": {
                "app_id": app.id,
                "app_name": app.name,
                "api_id": api_item.id,
                "api_name": api_item.name,
                "method": api_item.http_method,
                "url": target_url,
            },
        }
        _record_runtime_audit(
            account_id=account_id,
            tenant_id=tenant_id,
            action="external_app_runtime.invoke",
            content={
                "trace_id": trace_id,
                "app_id": app.id,
                "api_id": api_item.id,
                "dry_run": True,
                "permission_level_actual": permission_level,
                "call_mode_actual": call_mode,
                "warnings": warnings,
            },
            invoke_from=invoke_from,
            created_ip=created_ip,
        )
        db.session.commit()
        return {"result": "success", **result_payload}

    try:
        response = _invoke_external_request(
            method=api_item.http_method,
            url=target_url,
            headers=headers,
            params=merged_query_params,
            json_payload=json_body,
            timeout_seconds=timeout_value,
        )
    except Exception as ex:
        logger.exception("runtime invoke failed app_id=%s api_id=%s", app.id, api_item.id)
        _record_runtime_audit(
            account_id=account_id,
            tenant_id=tenant_id,
            action="external_app_runtime.invoke",
            content={
                "trace_id": trace_id,
                "app_id": app.id,
                "api_id": api_item.id,
                "dry_run": False,
                "permission_level_actual": permission_level,
                "call_mode_actual": call_mode,
                "warnings": warnings + [f"request_error:{type(ex).__name__}"],
            },
            invoke_from=invoke_from,
            created_ip=created_ip,
        )
        db.session.commit()
        raise ToolInvokeError("Failed to invoke external app api.") from ex

    response_payload = _decode_invoke_response_payload(response)

    business_status, business_code, business_message, business_failure_reason = _evaluate_business_result(
        response_payload
    )
    used_context_token_authorization = (
        bool(context_token_authorization) and headers.get("Authorization") == context_token_authorization
    )
    should_retry_with_context_token = (
        app.auth_mode.value == "static_bearer"
        and bool(context_token_authorization)
        and not used_context_token_authorization
        and _is_auth_failure_response(
            status_code=getattr(response, "status_code", None),
            business_code=business_code,
            business_message=business_message,
            response_payload=response_payload,
        )
    )
    if should_retry_with_context_token and context_token_authorization:
        retry_headers = dict(headers)
        retry_headers["Authorization"] = context_token_authorization
        warnings.append("static_bearer_business_auth_failed_context_token_retry")
        try:
            response = _invoke_external_request(
                method=api_item.http_method,
                url=target_url,
                headers=retry_headers,
                params=merged_query_params,
                json_payload=json_body,
                timeout_seconds=timeout_value,
            )
            headers = retry_headers
            response_payload = _decode_invoke_response_payload(response)
            business_status, business_code, business_message, business_failure_reason = _evaluate_business_result(
                response_payload
            )
        except Exception as ex:
            logger.exception("runtime invoke retry with context token failed app_id=%s api_id=%s", app.id, api_item.id)
            warnings.append(f"context_token_retry_request_error:{type(ex).__name__}")

    business_failed = business_status == "failed"
    if business_failed and business_failure_reason:
        warnings.append(f"business_error:{_truncate_optional_text(business_failure_reason, limit=200)}")

    _record_runtime_audit(
        account_id=account_id,
        tenant_id=tenant_id,
        action="external_app_runtime.invoke",
        content={
            "trace_id": trace_id,
            "app_id": app.id,
            "api_id": api_item.id,
            "dry_run": False,
            "permission_level_actual": permission_level,
            "call_mode_actual": call_mode,
            "warnings": warnings,
            "response_status": response.status_code,
            "business_status": business_status,
            "business_code": business_code,
            "business_message": _truncate_optional_text(business_message),
            "business_failed": business_failed,
        },
        invoke_from=invoke_from,
        created_ip=created_ip,
    )
    db.session.commit()

    return {
        "result": "failed" if business_failed else "success",
        "trace_id": trace_id,
        "permission_level_actual": permission_level,
        "call_mode_actual": call_mode,
        "warnings": warnings,
        "status_code": response.status_code,
        "business_status": business_status,
        "business_code": business_code,
        "business_message": business_message,
        "data": response_payload,
    }
