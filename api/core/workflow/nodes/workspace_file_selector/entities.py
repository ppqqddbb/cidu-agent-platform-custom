from typing import Any

from graphon.entities.base_node_data import BaseNodeData
from graphon.enums import NodeType

from . import WORKSPACE_FILE_SELECTOR_NODE_TYPE


class WorkspaceFileSelectorNodeData(BaseNodeData):
    type: NodeType = WORKSPACE_FILE_SELECTOR_NODE_TYPE
    file_id: str | None = None
    file_ids: list[str] | None = None
    selected_file: dict[str, Any] | None = None
