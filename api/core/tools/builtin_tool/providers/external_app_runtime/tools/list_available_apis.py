from collections.abc import Generator
from typing import Any

from core.tools.builtin_tool.tool import BuiltinTool
from core.tools.entities.tool_entities import ToolInvokeMessage
from core.tools.errors import ToolInvokeError

from .runtime_common import list_available_apis


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


class ListAvailableApisTool(BuiltinTool):
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

        query = tool_parameters.get("query")
        context_token = tool_parameters.get("context_token")
        max_results = int(tool_parameters.get("max_results") or 50)
        only_allowed = _parse_bool_parameter(tool_parameters.get("only_allowed"), False)

        result = list_available_apis(
            tenant_id=self.runtime.tenant_id,
            query=query if isinstance(query, str) else None,
            context_token=context_token if isinstance(context_token, str) and context_token.strip() else None,
            max_results=max_results,
            only_allowed=only_allowed,
        )
        yield self.create_json_message(result)
