import time
from unittest.mock import patch

from core.datasource.datasource_manager import DatasourceManager
from core.workflow.node_factory import LATEST_VERSION, get_node_type_classes_mapping
from core.workflow.nodes.workspace_file_selector import WORKSPACE_FILE_SELECTOR_NODE_TYPE
from core.workflow.nodes.workspace_file_selector.entities import WorkspaceFileSelectorNodeData
from core.workflow.nodes.workspace_file_selector.workspace_file_selector_node import WorkspaceFileSelectorNode
from graphon.enums import WorkflowNodeExecutionStatus
from graphon.file import File, FileTransferMethod, FileType
from graphon.nodes.document_extractor import DocumentExtractorNode, DocumentExtractorNodeData
from graphon.runtime import GraphRuntimeState, VariablePool
from tests.workflow_test_utils import build_test_graph_init_params


def _runtime_state() -> GraphRuntimeState:
    return GraphRuntimeState(variable_pool=VariablePool(), start_at=time.perf_counter())


def _node(config: WorkspaceFileSelectorNodeData) -> WorkspaceFileSelectorNode:
    return WorkspaceFileSelectorNode(
        node_id="file-selector",
        config=config,
        graph_init_params=build_test_graph_init_params(tenant_id="tenant-1"),
        graph_runtime_state=_runtime_state(),
    )


def _file(file_id: str = "file-1") -> File:
    return File(
        file_id=file_id,
        file_type=FileType.CUSTOM,
        transfer_method=FileTransferMethod.LOCAL_FILE,
        reference=file_id,
        filename=f"{file_id}.txt",
        extension=".txt",
        mime_type="text/plain",
        size=12,
        storage_key=f"workspace_files/tenant-1/{file_id}.txt",
    )


def test_run_fails_when_file_id_is_missing():
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
        )
    )

    result = node._run()

    assert result.status == WorkflowNodeExecutionStatus.FAILED
    assert result.error == "Workspace file is required."


def test_run_returns_file_output_when_workspace_file_is_visible():
    file_info = _file()
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
            file_id="file-1",
            selected_file={"id": "file-1", "name": "doc.txt"},
        )
    )

    with (
        patch.object(WorkspaceFileSelectorNode, "_ensure_workspace_file_visible", return_value=True),
        patch.object(DatasourceManager, "get_upload_file_by_id", return_value=file_info) as get_file,
    ):
        result = node._run()

    assert result.status == WorkflowNodeExecutionStatus.SUCCEEDED
    assert result.outputs == {"file": file_info}
    assert node.graph_runtime_state.variable_pool.get(["file-selector", "file"]).value == file_info
    assert node.graph_runtime_state.variable_pool.get(["file-selector", "files"]) is None
    get_file.assert_called_once_with(file_id="file-1", tenant_id="tenant-1")


def test_run_fails_when_workspace_file_is_not_visible():
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
            file_id="file-1",
        )
    )

    with (
        patch.object(WorkspaceFileSelectorNode, "_ensure_workspace_file_visible", return_value=False),
        patch.object(DatasourceManager, "get_upload_file_by_id") as get_file,
    ):
        result = node._run()

    assert result.status == WorkflowNodeExecutionStatus.FAILED
    assert result.error == "Workspace file not found."
    get_file.assert_not_called()


def test_legacy_file_ids_uses_first_file_only():
    file_2 = _file("file-2")
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
            file_ids=["file-2", "file-3"],
        )
    )

    with (
        patch.object(WorkspaceFileSelectorNode, "_ensure_workspace_file_visible", return_value=True) as visible,
        patch.object(DatasourceManager, "get_upload_file_by_id", return_value=file_2) as get_file,
    ):
        result = node._run()

    assert result.status == WorkflowNodeExecutionStatus.SUCCEEDED
    assert result.outputs == {"file": file_2}
    assert node.graph_runtime_state.variable_pool.get(["file-selector", "file"]).value == file_2
    assert result.inputs["file_id"] == "file-2"
    visible.assert_called_once_with(file_id="file-2", tenant_id="tenant-1")
    get_file.assert_called_once_with(file_id="file-2", tenant_id="tenant-1")


def test_legacy_file_ids_ignores_empty_values():
    file_3 = _file("file-3")
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
            file_ids=["", "file-3"],
        )
    )

    with (
        patch.object(WorkspaceFileSelectorNode, "_ensure_workspace_file_visible", return_value=True) as visible,
        patch.object(DatasourceManager, "get_upload_file_by_id", return_value=file_3) as get_file,
    ):
        result = node._run()

    assert result.status == WorkflowNodeExecutionStatus.SUCCEEDED
    assert result.outputs == {"file": file_3}
    assert result.inputs["file_id"] == "file-3"
    visible.assert_called_once_with(file_id="file-3", tenant_id="tenant-1")
    get_file.assert_called_once_with(file_id="file-3", tenant_id="tenant-1")


def test_run_uses_legacy_file_id_when_file_ids_are_missing():
    file_info = _file("file-1")
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
            file_id="file-1",
        )
    )

    with (
        patch.object(WorkspaceFileSelectorNode, "_ensure_workspace_file_visible", return_value=True) as visible,
        patch.object(DatasourceManager, "get_upload_file_by_id", return_value=file_info) as get_file,
    ):
        result = node._run()

    assert result.status == WorkflowNodeExecutionStatus.SUCCEEDED
    assert result.outputs == {"file": file_info}
    assert result.inputs["file_id"] == "file-1"
    visible.assert_called_once_with(file_id="file-1", tenant_id="tenant-1")
    get_file.assert_called_once_with(file_id="file-1", tenant_id="tenant-1")


def test_document_extractor_can_read_selected_file_from_variable_pool():
    file_info = _file("file-1")
    node = _node(
        WorkspaceFileSelectorNodeData(
            type=WORKSPACE_FILE_SELECTOR_NODE_TYPE,
            title="Workspace File",
            file_id="file-1",
        )
    )

    with (
        patch.object(WorkspaceFileSelectorNode, "_ensure_workspace_file_visible", return_value=True),
        patch.object(DatasourceManager, "get_upload_file_by_id", return_value=file_info),
    ):
        selector_result = node._run()

    assert selector_result.status == WorkflowNodeExecutionStatus.SUCCEEDED

    document_extractor_node = DocumentExtractorNode(
        node_id="document-extractor",
        config=DocumentExtractorNodeData(
            title="Document Extractor",
            variable_selector=["file-selector", "file"],
        ),
        graph_init_params=build_test_graph_init_params(tenant_id="tenant-1"),
        graph_runtime_state=node.graph_runtime_state,
    )

    with patch(
        "graphon.nodes.document_extractor.node._extract_text_from_file",
        return_value="file text",
    ) as extract_text:
        extractor_result = document_extractor_node._run()

    assert extractor_result.status == WorkflowNodeExecutionStatus.SUCCEEDED
    assert extractor_result.outputs == {"text": "file text"}
    assert extract_text.call_count == 1


def test_node_is_registered():
    mapping = get_node_type_classes_mapping()

    assert mapping[WORKSPACE_FILE_SELECTOR_NODE_TYPE][LATEST_VERSION] is WorkspaceFileSelectorNode
