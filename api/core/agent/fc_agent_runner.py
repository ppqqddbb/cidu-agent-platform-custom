import json
import logging
import re
from collections.abc import Generator, Mapping
from copy import deepcopy
from typing import Any, Union

from sqlalchemy.orm import Session

from core.agent.base_agent_runner import BaseAgentRunner
from core.agent.errors import AgentMaxIterationError
from core.app.apps.base_app_queue_manager import PublishFrom
from core.app.entities.queue_entities import QueueAgentThoughtEvent, QueueMessageEndEvent, QueueMessageFileEvent
from core.plugin.impl.exc import PluginDaemonInternalServerError, PluginInvokeError
from core.prompt.agent_history_prompt_transform import AgentHistoryPromptTransform
from core.tools.entities.tool_entities import ToolInvokeMeta, ToolProviderType
from core.tools.tool_engine import ToolEngine
from graphon.file import file_manager
from graphon.model_runtime.entities import (
    AssistantPromptMessage,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage,
    PromptMessage,
    PromptMessageContentType,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from graphon.model_runtime.entities.message_entities import ImagePromptMessageContent, PromptMessageContentUnionTypes
from models.model import Message

logger = logging.getLogger(__name__)

_EXTERNAL_APP_RUNTIME_TOOL_POLICY = (
    "When using external app runtime tools, follow this strict order: "
    "(1) Call list_available_apis first with only_allowed=false to discover app_id/api_id candidates. "
    "(2) Prefer candidates with allowed=true and higher routing_score. "
    "(3) If summary.next_action is available, use it as the first invoke_api candidate. "
    "(4) Call invoke_api immediately when required params are ready; "
    "for GET/HEAD/OPTIONS prefer dry_run=false, and for write methods prefer dry_run=true first. "
    "(5) If invoke_api reports missing_required_params, ask only for those missing fields. "
    "(6) If multiple candidates are plausible, explicitly explain that multiple APIs match, list key differences "
    "(app_name, api_name, method, path, and purpose), and ask the user to choose or provide narrowing conditions "
    "before invoking. "
    "(7) Before invoking, check invoke_hint.missing_required_params, auth_missing_fields, and warnings; "
    "explicitly tell the user which conditions are missing and what input is required. "
    "(8) If list_available_apis.summary.context_token_provided is true, "
    "do NOT ask the user to provide context_token again. "
    "If summary.context_token_status is provided_not_verified_missing_secret, "
    "explicitly state this is a server configuration issue "
    "(EXTERNAL_APP_CONTEXT_TOKEN_SECRET missing) rather than a user input issue. "
    "(9) In the final answer, include trace_id, permission_level_actual, and call_mode_actual when available."
)
_TOOL_CALL_LOOP_GUARD_ROUNDS = 3
_EXTERNAL_APP_CONTEXT_TOKEN_CANDIDATE_KEYS = (
    "context_token",
    "contextToken",
    "token_or_context_token",
    "tokenOrContextToken",
    "bearer_token",
    "bearerToken",
    "access_token",
    "accessToken",
    "token",
    "authorization",
    "Authorization",
)


class FunctionCallAgentRunner(BaseAgentRunner):
    @staticmethod
    def _extract_external_app_context_token_from_mapping(raw_mapping: Mapping[str, Any]) -> str | None:
        for key in _EXTERNAL_APP_CONTEXT_TOKEN_CANDIDATE_KEYS:
            raw_value = raw_mapping.get(key)
            if not isinstance(raw_value, str):
                continue
            normalized = raw_value.strip()
            if normalized:
                return normalized

        raw_auth_config = raw_mapping.get("auth_config")
        if isinstance(raw_auth_config, Mapping):
            for key in ("token", "token_or_context_token", "context_token", "authorization", "Authorization"):
                raw_value = raw_auth_config.get(key)
                if not isinstance(raw_value, str):
                    continue
                normalized = raw_value.strip()
                if normalized:
                    return normalized

        raw_headers = raw_mapping.get("headers")
        if isinstance(raw_headers, Mapping):
            for key in ("Authorization", "authorization"):
                raw_value = raw_headers.get(key)
                if not isinstance(raw_value, str):
                    continue
                normalized = raw_value.strip()
                if normalized:
                    return normalized

        return None

    def _resolve_external_app_context_token_from_inputs(self) -> str | None:
        raw_inputs = getattr(self.application_generate_entity, "inputs", None)
        if not isinstance(raw_inputs, Mapping):
            return None

        return self._extract_external_app_context_token_from_mapping(raw_inputs)

    def _prepare_external_app_runtime_tool_args(
        self, tool_call_name: str, tool_call_args: dict[str, Any]
    ) -> dict[str, Any]:
        if tool_call_name not in {"list_available_apis", "invoke_api"}:
            return tool_call_args

        prepared_args = dict(tool_call_args)
        context_token = prepared_args.get("context_token")
        if isinstance(context_token, str) and context_token.strip():
            return prepared_args

        fallback_context_token = self._resolve_external_app_context_token_from_inputs()
        if fallback_context_token:
            prepared_args["context_token"] = fallback_context_token
        return prepared_args

    @staticmethod
    def _build_fallback_answer_from_tool_response(tool_response_text: str) -> str:
        normalized = tool_response_text.strip()
        if not normalized:
            return ""

        try:
            payload = json.loads(normalized)
        except Exception:
            return f"工具已执行，结果如下：\n{normalized[:1200]}"

        if not isinstance(payload, dict):
            return f"工具已执行，结果如下：\n{normalized[:1200]}"

        result = payload.get("result")
        trace_id = payload.get("trace_id")
        status_code = payload.get("status_code")
        permission_level_actual = payload.get("permission_level_actual")
        call_mode_actual = payload.get("call_mode_actual")
        business_message = payload.get("business_message")

        if result == "failed":
            if isinstance(business_message, str) and business_message.strip():
                answer = f"接口调用失败：{business_message.strip()}。"
            else:
                answer = "接口调用失败，请检查下游业务系统日志。"
        else:
            answer = "工具调用已完成。"

        details: list[str] = []
        if isinstance(status_code, (int, float)):
            details.append(f"HTTP {int(status_code)}")
        if isinstance(permission_level_actual, str) and permission_level_actual.strip():
            details.append(f"权限={permission_level_actual.strip()}")
        if isinstance(call_mode_actual, str) and call_mode_actual.strip():
            details.append(f"模式={call_mode_actual.strip()}")
        if isinstance(trace_id, str) and trace_id.strip():
            details.append(f"trace_id={trace_id.strip()}")

        if details:
            answer += f"（{'，'.join(details)}）"

        return answer

    @staticmethod
    def _should_fallback_to_last_tool_response_on_llm_error(error: Exception) -> bool:
        if isinstance(error, (PluginDaemonInternalServerError, PluginInvokeError)):
            return True

        if isinstance(error, ValueError):
            normalized = str(error).strip().lower()
            return any(
                marker in normalized
                for marker in (
                    "plugin daemon",
                    "killed by timeout",
                    "use of closed network connection",
                    "failed to read system header",
                    "request to plugin daemon service failed",
                )
            )

        return False

    def run(
        self, session: Session, message: Message, query: str, **kwargs: Any
    ) -> Generator[LLMResultChunk, None, None]:
        """
        Run FunctionCall agent application
        """
        self.query = query
        app_generate_entity = self.application_generate_entity

        app_config = self.app_config
        assert app_config is not None, "app_config is required"
        assert app_config.agent is not None, "app_config.agent is required"

        # convert tools into ModelRuntime Tool format
        tool_instances, prompt_messages_tools = self._init_prompt_tools()

        assert app_config.agent

        iteration_step = 1
        max_iteration_steps = min(app_config.agent.max_iteration, 99) + 1

        # continue to run until there is not any tool call
        function_call_state = True
        llm_usage: dict[str, LLMUsage | None] = {"usage": None}
        final_answer = ""
        last_tool_response_text: str | None = None
        last_tool_call_signature: str | None = None
        same_tool_call_rounds = 0
        stopped_by_tool_loop_guard = False
        prompt_messages: list = []  # Initialize prompt_messages

        # get tracing instance
        trace_manager = app_generate_entity.trace_manager

        def increase_usage(final_llm_usage_dict: dict[str, LLMUsage | None], usage: LLMUsage):
            if not final_llm_usage_dict["usage"]:
                final_llm_usage_dict["usage"] = usage
            else:
                llm_usage = final_llm_usage_dict["usage"]
                llm_usage.prompt_tokens += usage.prompt_tokens
                llm_usage.completion_tokens += usage.completion_tokens
                llm_usage.total_tokens += usage.total_tokens
                llm_usage.prompt_price += usage.prompt_price
                llm_usage.completion_price += usage.completion_price
                llm_usage.total_price += usage.total_price

        model_instance = self.model_instance

        while function_call_state and iteration_step <= max_iteration_steps:
            function_call_state = False

            if iteration_step == max_iteration_steps:
                # the last iteration, remove all tools
                prompt_messages_tools = []

            message_file_ids: list[str] = []
            agent_thought_id = self.create_agent_thought(
                message_id=message.id,
                message="",
                tool_name="",
                tool_input="",
                messages_ids=message_file_ids,
            )

            # recalc llm max tokens
            prompt_messages = self._organize_prompt_messages()
            self.recalc_llm_max_tokens(self.model_config, prompt_messages)

            # Release any setup/tool transaction before waiting on the provider stream.
            session.commit()
            session.close()
            tool_calls: list[tuple[str, str, dict[str, Any]]] = []

            # save full response
            response = ""

            # save tool call names and inputs
            tool_call_names = ""
            tool_call_inputs = ""

            current_llm_usage = None
            try:
                # invoke model
                chunks: Union[Generator[LLMResultChunk, None, None], LLMResult] = model_instance.invoke_llm(
                    prompt_messages=prompt_messages,
                    model_parameters=app_generate_entity.model_conf.parameters,
                    tools=prompt_messages_tools,
                    stop=app_generate_entity.model_conf.stop,
                    stream=self.stream_tool_call,
                    callbacks=[],
                    request_metadata={"app_id": self.app_config.app_id},
                )

                if isinstance(chunks, Generator):
                    is_first_chunk = True
                    for chunk in chunks:
                        if is_first_chunk:
                            self.queue_manager.publish(
                                QueueAgentThoughtEvent(agent_thought_id=agent_thought_id),
                                PublishFrom.APPLICATION_MANAGER,
                            )
                            is_first_chunk = False
                        # check if there is any tool call
                        if self.check_tool_calls(chunk):
                            function_call_state = True
                            tool_calls.extend(self.extract_tool_calls(chunk) or [])
                            tool_call_names = ";".join([tool_call[1] for tool_call in tool_calls])
                            try:
                                tool_call_inputs = json.dumps(
                                    {tool_call[1]: tool_call[2] for tool_call in tool_calls}, ensure_ascii=False
                                )
                            except TypeError:
                                # fallback: force ASCII to handle non-serializable objects
                                tool_call_inputs = json.dumps(
                                    {tool_call[1]: tool_call[2] for tool_call in tool_calls}
                                )

                        if chunk.delta.message and chunk.delta.message.content:
                            if isinstance(chunk.delta.message.content, list):
                                for content in chunk.delta.message.content:
                                    response += content.data
                            else:
                                response += str(chunk.delta.message.content)

                        if chunk.delta.usage:
                            increase_usage(llm_usage, chunk.delta.usage)
                            current_llm_usage = chunk.delta.usage

                        yield chunk
                else:
                    result = chunks
                    # check if there is any tool call
                    if self.check_blocking_tool_calls(result):
                        function_call_state = True
                        tool_calls.extend(self.extract_blocking_tool_calls(result) or [])
                        tool_call_names = ";".join([tool_call[1] for tool_call in tool_calls])
                        try:
                            tool_call_inputs = json.dumps(
                                {tool_call[1]: tool_call[2] for tool_call in tool_calls}, ensure_ascii=False
                            )
                        except TypeError:
                            # fallback: force ASCII to handle non-serializable objects
                            tool_call_inputs = json.dumps({tool_call[1]: tool_call[2] for tool_call in tool_calls})

                    if result.usage:
                        increase_usage(llm_usage, result.usage)
                        current_llm_usage = result.usage

                    if result.message and result.message.content:
                        if isinstance(result.message.content, list):
                            for content in result.message.content:
                                response += content.data
                        else:
                            response += str(result.message.content)

                    if not result.message.content:
                        result.message.content = ""

                    self.queue_manager.publish(
                        QueueAgentThoughtEvent(agent_thought_id=agent_thought_id), PublishFrom.APPLICATION_MANAGER
                    )

                    yield LLMResultChunk(
                        model=model_instance.model_name,
                        prompt_messages=result.prompt_messages,
                        system_fingerprint=result.system_fingerprint,
                        delta=LLMResultChunkDelta(
                            index=0,
                            message=result.message,
                            usage=result.usage,
                        ),
                    )
            except Exception as ex:
                if last_tool_response_text and self._should_fallback_to_last_tool_response_on_llm_error(ex):
                    logger.exception(
                        "LLM invoke failed after tool response, fallback to last tool response. step=%s",
                        iteration_step,
                    )
                    function_call_state = False
                    break
                raise

            if not tool_calls and response:
                text_tool_calls = self._extract_text_tool_calls_from_content(response)
                if text_tool_calls:
                    function_call_state = True
                    tool_calls.extend(text_tool_calls)
                    tool_call_names = ";".join([tool_call[1] for tool_call in tool_calls])
                    try:
                        tool_call_inputs = json.dumps(
                            {tool_call[1]: tool_call[2] for tool_call in tool_calls}, ensure_ascii=False
                        )
                    except TypeError:
                        tool_call_inputs = json.dumps({tool_call[1]: tool_call[2] for tool_call in tool_calls})

            if tool_calls:
                current_tool_call_signature = self._build_tool_call_signature(tool_calls)
                if current_tool_call_signature == last_tool_call_signature:
                    same_tool_call_rounds += 1
                else:
                    same_tool_call_rounds = 1
                    last_tool_call_signature = current_tool_call_signature
            else:
                same_tool_call_rounds = 0
                last_tool_call_signature = None

            assistant_message = AssistantPromptMessage(content=response, tool_calls=[])
            if tool_calls:
                assistant_message.tool_calls = [
                    AssistantPromptMessage.ToolCall(
                        id=tool_call[0],
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=tool_call[1], arguments=json.dumps(tool_call[2], ensure_ascii=False)
                        ),
                    )
                    for tool_call in tool_calls
                ]

            self._current_thoughts.append(assistant_message)

            # save thought
            self.save_agent_thought(
                agent_thought_id=agent_thought_id,
                tool_name=tool_call_names,
                tool_input=tool_call_inputs,
                thought=response,
                tool_invoke_meta=None,
                observation=None,
                answer=response,
                messages_ids=[],
                llm_usage=current_llm_usage,
            )
            self.queue_manager.publish(
                QueueAgentThoughtEvent(agent_thought_id=agent_thought_id), PublishFrom.APPLICATION_MANAGER
            )

            final_answer += response + "\n"

            if tool_calls and same_tool_call_rounds >= _TOOL_CALL_LOOP_GUARD_ROUNDS:
                logger.warning(
                    "Detected repeated tool-call loop, force stop. step=%s, rounds=%s, signature=%s",
                    iteration_step,
                    same_tool_call_rounds,
                    last_tool_call_signature,
                )
                tool_calls = []
                function_call_state = False
                stopped_by_tool_loop_guard = True

            # Check if max iteration is reached and model still wants to call tools
            if iteration_step == max_iteration_steps and tool_calls:
                if last_tool_response_text:
                    logger.warning(
                        "Max iteration reached with tool calls, fallback to last tool response. step=%s",
                        iteration_step,
                    )
                    tool_calls = []
                    function_call_state = False
                else:
                    raise AgentMaxIterationError(app_config.agent.max_iteration)

            # call tools
            tool_responses = []
            for tool_call_id, tool_call_name, tool_call_args in tool_calls:
                tool_instance = tool_instances.get(tool_call_name)
                if not tool_instance:
                    tool_response = {
                        "tool_call_id": tool_call_id,
                        "tool_call_name": tool_call_name,
                        "tool_response": f"there is not a tool named {tool_call_name}",
                        "meta": ToolInvokeMeta.error_instance(f"there is not a tool named {tool_call_name}").to_dict(),
                    }
                else:
                    prepared_tool_call_args = self._prepare_external_app_runtime_tool_args(
                        tool_call_name, tool_call_args
                    )
                    # invoke tool
                    tool_invoke_response, message_files, tool_invoke_meta = ToolEngine.agent_invoke(
                        session=session,
                        tool=tool_instance,
                        tool_parameters=prepared_tool_call_args,
                        user_id=self.user_id,
                        tenant_id=self.tenant_id,
                        message=self.message,
                        invoke_from=self.application_generate_entity.invoke_from,
                        agent_tool_callback=self.agent_callback,
                        trace_manager=trace_manager,
                        app_id=self.application_generate_entity.app_config.app_id,
                        message_id=self.message.id,
                        conversation_id=self.conversation.id,
                    )
                    session.commit()
                    session.close()
                    # publish files
                    for message_file_id in message_files:
                        # publish message file
                        self.queue_manager.publish(
                            QueueMessageFileEvent(message_file_id=message_file_id), PublishFrom.APPLICATION_MANAGER
                        )
                        # add message file ids
                        message_file_ids.append(message_file_id)

                    tool_response = {
                        "tool_call_id": tool_call_id,
                        "tool_call_name": tool_call_name,
                        "tool_response": tool_invoke_response,
                        "meta": tool_invoke_meta.to_dict(),
                    }

                tool_responses.append(tool_response)
                if tool_response["tool_response"] is not None:
                    tool_response_text = str(tool_response["tool_response"])
                    if tool_response_text.strip():
                        last_tool_response_text = tool_response_text
                    self._current_thoughts.append(
                        ToolPromptMessage(
                            content=tool_response_text,
                            tool_call_id=tool_call_id,
                            name=tool_call_name,
                        )
                    )

            if len(tool_responses) > 0:
                if len(tool_responses) == 1:
                    single_observation: str | dict[str, Any] = tool_responses[0]["tool_response"]
                else:
                    single_observation = {
                        tool_response["tool_call_name"]: tool_response["tool_response"]
                        for tool_response in tool_responses
                    }
                # save agent thought
                self.save_agent_thought(
                    agent_thought_id=agent_thought_id,
                    tool_name="",
                    tool_input="",
                    thought="",
                    tool_invoke_meta={
                        tool_response["tool_call_name"]: tool_response["meta"] for tool_response in tool_responses
                    },
                    observation=single_observation,
                    answer="",
                    messages_ids=message_file_ids,
                )
                self.queue_manager.publish(
                    QueueAgentThoughtEvent(agent_thought_id=agent_thought_id), PublishFrom.APPLICATION_MANAGER
                )

            # update prompt tool
            for prompt_tool in prompt_messages_tools:
                tool_instance = tool_instances.get(prompt_tool.name)
                if tool_instance:
                    self.update_prompt_message_tool(tool_instance, prompt_tool)

            iteration_step += 1

        if not final_answer.strip() and last_tool_response_text:
            fallback_answer = self._build_fallback_answer_from_tool_response(last_tool_response_text)
            if fallback_answer.strip():
                final_answer = fallback_answer
        if stopped_by_tool_loop_guard and not final_answer.strip():
            final_answer = (
                "Tool call loop detected and stopped to avoid infinite execution. "
                "Please refine your question or provide more required parameters."
            )

        # publish end event
        self.queue_manager.publish(
            QueueMessageEndEvent(
                llm_result=LLMResult(
                    model=model_instance.model_name,
                    prompt_messages=prompt_messages,
                    message=AssistantPromptMessage(content=final_answer),
                    usage=llm_usage["usage"] or LLMUsage.empty_usage(),
                    system_fingerprint="",
                )
            ),
            PublishFrom.APPLICATION_MANAGER,
        )

    def check_tool_calls(self, llm_result_chunk: LLMResultChunk) -> bool:
        """
        Check if there is any tool call in llm result chunk
        """
        if llm_result_chunk.delta.message.tool_calls:
            return True
        if self._extract_text_tool_calls_from_content(llm_result_chunk.delta.message.content):
            return True
        return False

    def check_blocking_tool_calls(self, llm_result: LLMResult) -> bool:
        """
        Check if there is any blocking tool call in llm result
        """
        if llm_result.message.tool_calls:
            return True
        if self._extract_text_tool_calls_from_content(llm_result.message.content):
            return True
        return False

    def extract_tool_calls(self, llm_result_chunk: LLMResultChunk) -> list[tuple[str, str, dict[str, Any]]]:
        """
        Extract tool calls from llm result chunk

        Returns:
            List[Tuple[str, str, Dict[str, Any]]]: [(tool_call_id, tool_call_name, tool_call_args)]
        """
        tool_calls = []
        for prompt_message in llm_result_chunk.delta.message.tool_calls:
            args = {}
            if prompt_message.function.arguments != "":
                args = json.loads(prompt_message.function.arguments)

            tool_calls.append(
                (
                    prompt_message.id,
                    prompt_message.function.name,
                    args,
                )
            )

        if not tool_calls:
            tool_calls.extend(self._extract_text_tool_calls_from_content(llm_result_chunk.delta.message.content))

        return tool_calls

    def extract_blocking_tool_calls(self, llm_result: LLMResult) -> list[tuple[str, str, dict[str, Any]]]:
        """
        Extract blocking tool calls from llm result

        Returns:
            List[Tuple[str, str, Dict[str, Any]]]: [(tool_call_id, tool_call_name, tool_call_args)]
        """
        tool_calls = []
        for prompt_message in llm_result.message.tool_calls:
            args = {}
            if prompt_message.function.arguments != "":
                args = json.loads(prompt_message.function.arguments)

            tool_calls.append(
                (
                    prompt_message.id,
                    prompt_message.function.name,
                    args,
                )
            )

        if not tool_calls:
            tool_calls.extend(self._extract_text_tool_calls_from_content(llm_result.message.content))

        return tool_calls

    @staticmethod
    def _coerce_text_tool_parameter_value(raw_value: str) -> Any:
        value = raw_value.strip()
        if value == "":
            return ""

        normalized = value.lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        if normalized == "null":
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _flatten_message_content_to_text(
        content: PromptMessageContentType | list[PromptMessageContentType] | None,
    ) -> str:
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                    continue

                data = getattr(item, "data", None)
                if isinstance(data, str):
                    texts.append(data)
            return "\n".join(texts)

        return str(content)

    @staticmethod
    def _build_tool_call_signature(tool_calls: list[tuple[str, str, dict[str, Any]]]) -> str:
        normalized_items: list[str] = []
        for _, tool_name, tool_args in tool_calls:
            serialized_args = "{}"
            if tool_args:
                try:
                    serialized_args = json.dumps(tool_args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                except TypeError:
                    serialized_args = str(tool_args)
            normalized_items.append(f"{tool_name}:{serialized_args}")

        return "|".join(normalized_items)

    def _extract_text_tool_calls_from_content(
        self,
        content: PromptMessageContentType | list[PromptMessageContentType] | None,
    ) -> list[tuple[str, str, dict[str, Any]]]:
        text = self._flatten_message_content_to_text(content)
        if not text:
            return []

        tool_call_pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.IGNORECASE | re.DOTALL)
        function_pattern = re.compile(r"<function=([^>\n]+)>", re.IGNORECASE)
        parameter_pattern = re.compile(
            r"<parameter=([^>\n]+)>([\s\S]*?)(?=(?:<parameter=[^>\n]+>|</tool_call>|$))",
            re.IGNORECASE,
        )

        parsed_calls: list[tuple[str, str, dict[str, Any]]] = []
        for index, block in enumerate(tool_call_pattern.finditer(text), start=1):
            block_content = block.group(1)
            function_match = function_pattern.search(block_content)
            if not function_match:
                continue

            function_name = function_match.group(1).strip()
            if not function_name:
                continue

            arguments: dict[str, Any] = {}
            for parameter in parameter_pattern.finditer(block_content):
                parameter_name = parameter.group(1).strip()
                if not parameter_name:
                    continue

                parameter_value = self._coerce_text_tool_parameter_value(parameter.group(2))
                arguments[parameter_name] = parameter_value

            parsed_calls.append((f"text-tool-call-{index}", function_name, arguments))

        return parsed_calls

    def _init_system_message(self, prompt_template: str, prompt_messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        Initialize system message
        """
        if not prompt_messages and prompt_template:
            return [
                SystemPromptMessage(content=prompt_template),
            ]

        if prompt_messages and not isinstance(prompt_messages[0], SystemPromptMessage) and prompt_template:
            prompt_messages.insert(0, SystemPromptMessage(content=prompt_template))

        return prompt_messages or []

    def _organize_user_query(self, query: str, prompt_messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        Organize user query
        """
        if self.files:
            # get image detail config
            image_detail_config = (
                self.application_generate_entity.file_upload_config.image_config.detail
                if (
                    self.application_generate_entity.file_upload_config
                    and self.application_generate_entity.file_upload_config.image_config
                )
                else None
            )
            image_detail_config = image_detail_config or ImagePromptMessageContent.DETAIL.LOW

            prompt_message_contents: list[PromptMessageContentUnionTypes] = []
            for file in self.files:
                prompt_message_contents.append(
                    file_manager.to_prompt_message_content(
                        file,
                        image_detail_config=image_detail_config,
                    )
                )
            prompt_message_contents.append(TextPromptMessageContent(data=query))

            prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
        else:
            prompt_messages.append(UserPromptMessage(content=query))

        return prompt_messages

    def _clear_user_prompt_image_messages(self, prompt_messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        As for now, gpt supports both fc and vision at the first iteration.
        We need to remove the image messages from the prompt messages at the first iteration.
        """
        prompt_messages = deepcopy(prompt_messages)

        for prompt_message in prompt_messages:
            if isinstance(prompt_message, UserPromptMessage):
                if isinstance(prompt_message.content, list):
                    prompt_message.content = "\n".join(
                        [
                            content.data
                            if content.type == PromptMessageContentType.TEXT
                            else "[image]"
                            if content.type == PromptMessageContentType.IMAGE
                            else "[file]"
                            for content in prompt_message.content
                        ]
                    )

        return prompt_messages

    def _organize_prompt_messages(self):
        prompt_template = self.app_config.prompt_template.simple_prompt_template or ""
        prompt_template = self._append_external_app_runtime_tool_policy(prompt_template)
        self.history_prompt_messages = self._init_system_message(prompt_template, self.history_prompt_messages)
        query_prompt_messages = self._organize_user_query(self.query or "", [])

        self.history_prompt_messages = AgentHistoryPromptTransform(
            model_config=self.model_config,
            prompt_messages=[*query_prompt_messages, *self._current_thoughts],
            history_messages=self.history_prompt_messages,
            memory=self.memory,
        ).get_prompt()

        prompt_messages = [*self.history_prompt_messages, *query_prompt_messages, *self._current_thoughts]
        if len(self._current_thoughts) != 0:
            # clear messages after the first iteration
            prompt_messages = self._clear_user_prompt_image_messages(prompt_messages)
        return prompt_messages

    def _append_external_app_runtime_tool_policy(self, prompt_template: str) -> str:
        """
        Append a deterministic tool-order policy when external app runtime tools are configured.
        """
        app_config = self.app_config
        if not app_config or not app_config.agent:
            return prompt_template

        agent_tools = getattr(app_config.agent, "tools", None)
        if not isinstance(agent_tools, list):
            return prompt_template

        configured_tools = set()
        for tool in agent_tools:
            provider_type = getattr(tool, "provider_type", None)
            provider_id = getattr(tool, "provider_id", None)
            tool_name = getattr(tool, "tool_name", None)
            if provider_type != ToolProviderType.BUILT_IN:
                continue
            if provider_id != "external_app_runtime":
                continue
            if isinstance(tool_name, str) and tool_name:
                configured_tools.add(tool_name)

        if not {"list_available_apis", "invoke_api"}.issubset(configured_tools):
            return prompt_template

        if _EXTERNAL_APP_RUNTIME_TOOL_POLICY in prompt_template:
            return prompt_template

        if prompt_template:
            return f"{prompt_template}\n\n{_EXTERNAL_APP_RUNTIME_TOOL_POLICY}"
        return _EXTERNAL_APP_RUNTIME_TOOL_POLICY
