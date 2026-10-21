import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.workflow.nodes.agent.runtime_support import AgentRuntimeSupport
from graphon.model_runtime.entities.model_entities import ModelType


def test_fetch_model_reuses_single_model_assembly():
    provider_configuration = SimpleNamespace(
        get_current_credentials=Mock(return_value={"api_key": "x"}),
        provider=SimpleNamespace(provider="openai"),
    )
    model_type_instance = SimpleNamespace(get_model_schema=Mock(return_value="schema"))
    provider_model_bundle = SimpleNamespace(
        configuration=provider_configuration,
        model_type_instance=model_type_instance,
    )
    model_instance = Mock()
    assembly = SimpleNamespace(
        provider_manager=Mock(),
        model_manager=Mock(),
    )
    assembly.provider_manager.get_provider_model_bundle.return_value = provider_model_bundle
    assembly.model_manager.get_model_instance.return_value = model_instance

    with patch(
        "core.workflow.nodes.agent.runtime_support.create_plugin_model_assembly",
        return_value=assembly,
    ) as mock_assembly:
        resolved_instance, resolved_schema = AgentRuntimeSupport().fetch_model(
            tenant_id="tenant-1",
            user_id="user-1",
            value={"provider": "openai", "model": "gpt-4o-mini", "model_type": "llm"},
        )

    assert resolved_instance is model_instance
    assert resolved_schema == "schema"
    mock_assembly.assert_called_once_with(tenant_id="tenant-1", user_id="user-1")
    assembly.provider_manager.get_provider_model_bundle.assert_called_once_with(
        tenant_id="tenant-1",
        provider="openai",
        model_type=ModelType.LLM,
    )
    assembly.model_manager.get_model_instance.assert_called_once_with(
        tenant_id="tenant-1",
        provider="openai",
        model_type=ModelType.LLM,
        model="gpt-4o-mini",
    )


def test_build_parameters_sanitizes_complex_tool_defaults_before_agent_strategy():
    selected_tools = [
        {
            "enabled": True,
            "type": "builtin",
            "provider_name": "external_app_runtime",
            "tool_name": "invoke_api",
            "parameters": {
                "app_id": {"auto": 1, "value": None},
                "params": {"auto": 1, "value": None},
                "dry_run": {"auto": 1, "value": None},
            },
            "settings": {},
        }
    ]
    serialized_tools = json.dumps(selected_tools, ensure_ascii=False)

    variable_pool = Mock()
    variable_pool.convert_template.return_value = SimpleNamespace(text=serialized_tools, log=serialized_tools)

    tool_runtime = SimpleNamespace(
        entity=SimpleNamespace(
            description=None,
            parameters=[
                SimpleNamespace(name="params", form="llm"),
                SimpleNamespace(name="dry_run", form="llm"),
            ],
            model_dump=Mock(
                return_value={
                    "identity": {"provider": "external_app_runtime", "name": "invoke_api"},
                    "parameters": [
                        {"name": "params", "type": "object", "default": {}},
                        {"name": "dry_run", "type": "boolean", "default": False},
                    ],
                }
            ),
        ),
        runtime=SimpleNamespace(runtime_parameters={}),
    )

    node_data = SimpleNamespace(
        agent_parameters={"tools": SimpleNamespace(type="constant", value=selected_tools)},
        version="0.6.0",
        tool_node_version="2",
        memory=None,
    )
    strategy = SimpleNamespace(meta_version=None)

    with patch(
        "core.workflow.nodes.agent.runtime_support.ToolManager.get_agent_tool_runtime",
        return_value=tool_runtime,
    ):
        result = AgentRuntimeSupport().build_parameters(
            agent_parameters=[SimpleNamespace(name="tools", type="array[tools]")],
            variable_pool=variable_pool,
            node_data=node_data,
            strategy=strategy,
            tenant_id="tenant-1",
            user_id="user-1",
            app_id="app-1",
            invoke_from="workflow",
        )

    assert result["tools"][0]["parameters"][0]["default"] is None
    assert result["tools"][0]["parameters"][1]["default"] is False


def test_build_parameters_injects_context_token_for_external_app_runtime_tools():
    selected_tools = [
        {
            "enabled": True,
            "type": "builtin",
            "provider_name": "external_app_runtime",
            "tool_name": "invoke_api",
            "parameters": {
                "app_id": {"auto": 1, "value": None},
                "api_id": {"auto": 1, "value": None},
                "context_token": {"auto": 1, "value": None},
                "params": {"auto": 1, "value": None},
            },
            "settings": {},
        }
    ]
    serialized_tools = json.dumps(selected_tools, ensure_ascii=False)

    variable_pool = Mock()
    variable_pool.get_by_prefix.return_value = {"context_token": "Bearer workflow-jwt"}
    variable_pool.convert_template.return_value = SimpleNamespace(text=serialized_tools, log=serialized_tools)

    tool_runtime = SimpleNamespace(
        entity=SimpleNamespace(
            description=None,
            parameters=[],
            model_dump=Mock(
                return_value={
                    "identity": {"provider": "external_app_runtime", "name": "invoke_api"},
                    "parameters": [],
                }
            ),
        ),
        runtime=SimpleNamespace(runtime_parameters={}),
    )

    node_data = SimpleNamespace(
        agent_parameters={"tools": SimpleNamespace(type="constant", value=selected_tools)},
        version="0.6.0",
        tool_node_version="2",
        memory=None,
    )
    strategy = SimpleNamespace(meta_version=None)

    with patch(
        "core.workflow.nodes.agent.runtime_support.ToolManager.get_agent_tool_runtime",
        return_value=tool_runtime,
    ) as mocked_get_runtime:
        AgentRuntimeSupport().build_parameters(
            agent_parameters=[SimpleNamespace(name="tools", type="array[tools]")],
            variable_pool=variable_pool,
            node_data=node_data,
            strategy=strategy,
            tenant_id="tenant-1",
            user_id="user-1",
            app_id="app-1",
            invoke_from="workflow",
        )

    agent_tool_entity = mocked_get_runtime.call_args.args[2]
    assert agent_tool_entity.tool_parameters["context_token"] == "Bearer workflow-jwt"
