from collections.abc import Generator
from typing import Any

from core.tools.builtin_tool.tool import BuiltinTool
from core.tools.entities.tool_entities import ToolInvokeMessage
from core.tools.errors import ToolInvokeError

from .runtime_common import invoke_api


def _parse_bool_parameter(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


class InvokeApiTool(BuiltinTool):
    def _invoke(
        self,
        user_id: str,
        tool_parameters: dict[str, Any],
        conversation_id: str | None = None,
        app_id: str | None = None,
        message_id: str | None = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        if self.runtime is None or not self.runtime.tenant_id:
            raise ToolInvokeError("Tool runtime tenant_id is required.")

        app_id_param = tool_parameters.get("app_id")
        api_id_param = tool_parameters.get("api_id")
        if not isinstance(app_id_param, str) or not app_id_param.strip():
            raise ToolInvokeError("app_id is required.")
        if not isinstance(api_id_param, str) or not api_id_param.strip():
            raise ToolInvokeError("api_id is required.")

        context_token = tool_parameters.get("context_token")
        params = tool_parameters.get("params")
        dry_run = _parse_bool_parameter(tool_parameters.get("dry_run"), False)

        timeout_seconds_param = tool_parameters.get("timeout_seconds")
        timeout_seconds: float | None = None
        if isinstance(timeout_seconds_param, (int, float)) and float(timeout_seconds_param) > 0:
            timeout_seconds = float(timeout_seconds_param)

        account_id = self.runtime.user_id or user_id
        if not isinstance(account_id, str) or not account_id.strip():
            raise ToolInvokeError("Tool runtime user_id is required for audit logging.")

        result = invoke_api(
            tenant_id=self.runtime.tenant_id,
            account_id=account_id,
            app_id=app_id_param.strip(),
            api_id=api_id_param.strip(),
            context_token=context_token if isinstance(context_token, str) and context_token.strip() else None,
            params=params,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            invoke_from="builtin_tool",
        )
        yield self.create_json_message(result)
