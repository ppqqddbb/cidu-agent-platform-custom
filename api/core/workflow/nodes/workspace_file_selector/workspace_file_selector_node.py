from sqlalchemy import and_, exists, or_, select

from core.app.entities.app_invoke_entities import DIFY_RUN_CONTEXT_KEY, DifyRunContext
from core.datasource.datasource_manager import DatasourceManager
from core.db.session_factory import session_factory
from graphon.enums import WorkflowNodeExecutionStatus
from graphon.node_events import NodeRunResult
from graphon.nodes.base.node import Node
from models.model import MessageFile, UploadFile

from . import WORKSPACE_FILE_SELECTOR_NODE_TYPE
from .entities import WorkspaceFileSelectorNodeData

WORKSPACE_FILE_STORAGE_NAMESPACE = "workspace_files"
LEGACY_UPLOAD_FILE_STORAGE_NAMESPACE = "upload_files"


def _workspace_file_key_prefix(tenant_id: str) -> str:
    return f"{WORKSPACE_FILE_STORAGE_NAMESPACE}/{tenant_id}/"


def _legacy_upload_file_key_prefix(tenant_id: str) -> str:
    return f"{LEGACY_UPLOAD_FILE_STORAGE_NAMESPACE}/{tenant_id}/"


def _workspace_visible_file_filter(tenant_id: str):
    message_file_exists = exists().where(MessageFile.upload_file_id == UploadFile.id)
    return or_(
        UploadFile.key.like(f"{_workspace_file_key_prefix(tenant_id)}%"),
        and_(
            UploadFile.key.like(f"{_legacy_upload_file_key_prefix(tenant_id)}%"),
            or_(
                UploadFile.file_type == "temporary",
                and_(UploadFile.file_type == "formal", ~message_file_exists),
            ),
        ),
    )


class WorkspaceFileSelectorNode(Node[WorkspaceFileSelectorNodeData]):
    node_type = WORKSPACE_FILE_SELECTOR_NODE_TYPE

    @classmethod
    def version(cls) -> str:
        return "1"

    def _run(self) -> NodeRunResult:
        dify_ctx = DifyRunContext.model_validate(self.require_run_context_value(DIFY_RUN_CONTEXT_KEY))
        file_id = self._resolve_file_id()
        inputs = {
            "file_id": file_id or "",
            "selected_file": self.node_data.selected_file or {},
        }

        if not file_id:
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs=inputs,
                error="Workspace file is required.",
                error_type="ValueError",
            )

        try:
            if not self._ensure_workspace_file_visible(file_id=file_id, tenant_id=dify_ctx.tenant_id):
                return NodeRunResult(
                    status=WorkflowNodeExecutionStatus.FAILED,
                    inputs=inputs,
                    error="Workspace file not found.",
                    error_type="ValueError",
                )

            file_info = DatasourceManager.get_upload_file_by_id(file_id=file_id, tenant_id=dify_ctx.tenant_id)
            variable_pool = self.graph_runtime_state.variable_pool
            variable_pool.add([self._node_id, "file"], file_info)

            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.SUCCEEDED,
                inputs=inputs,
                outputs={
                    "file": file_info,
                },
            )
        except Exception as e:
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs=inputs,
                error=str(e),
                error_type=type(e).__name__,
            )

    def _resolve_file_id(self) -> str | None:
        if self.node_data.file_id:
            return self.node_data.file_id

        for file_id in self.node_data.file_ids or []:
            if file_id:
                return file_id
        return None

    @staticmethod
    def _ensure_workspace_file_visible(*, file_id: str, tenant_id: str) -> bool:
        with session_factory.create_session() as session:
            stmt = (
                select(UploadFile.id)
                .where(
                    UploadFile.id == file_id,
                    UploadFile.tenant_id == tenant_id,
                    _workspace_visible_file_filter(tenant_id),
                )
                .limit(1)
            )
            return session.scalar(stmt) is not None
