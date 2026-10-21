"""Workflow nodes for standalone knowledge graph retrieval.

Graph retrieval is intentionally implemented separately from dataset retrieval. The node adapts graph hits into the
same `result` output shape as knowledge retrieval only at the workflow boundary so downstream LLM and answer nodes can
consume either source without owning graph-specific details.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from core.app.entities.app_invoke_entities import DIFY_RUN_CONTEXT_KEY, DifyRunContext
from core.knowledge_graph.entities import GraphRetrievalRequest, GraphRetrievalResult
from core.workflow.nodes.knowledge_retrieval.retrieval import Source, SourceMetadata
from graphon.enums import WorkflowNodeExecutionStatus
from graphon.model_runtime.entities.llm_entities import LLMUsage
from graphon.model_runtime.utils.encoders import jsonable_encoder
from graphon.node_events import NodeRunResult
from graphon.nodes.base import LLMUsageTrackingMixin
from graphon.nodes.base.node import Node
from graphon.variables import StringSegment
from graphon.variables.segments import ArrayObjectSegment
from services.knowledge_graph_service import KnowledgeGraphService

from .entities import KNOWLEDGE_GRAPH_RETRIEVAL_NODE_TYPE, KnowledgeGraphRetrievalNodeData

if TYPE_CHECKING:
    from graphon.entities import GraphInitParams
    from graphon.runtime import GraphRuntimeState

logger = logging.getLogger(__name__)


def graph_result_to_source(result: GraphRetrievalResult) -> Source:
    """Adapt a graph retrieval hit into the workflow retrieval output contract."""
    document_id = str(result.metadata.get("relation_id") or result.metadata.get("source_id") or result.graph_id)
    segment_id = result.metadata.get("relation_id") or result.metadata.get("source_id")
    metadata = {
        **jsonable_encoder(result.metadata),
        "graph_id": result.graph_id,
        "graph_title": result.title,
        "source_type": "knowledge_graph",
    }
    return Source(
        metadata=SourceMetadata(
            source="knowledge_graph",
            dataset_id=result.graph_id,
            dataset_name=result.title,
            document_id=document_id,
            document_name=result.title,
            data_source_type="knowledge_graph",
            segment_id=str(segment_id) if segment_id is not None else None,
            score=result.score,
            doc_metadata=metadata,
        ),
        title=result.title,
        files=None,
        content=result.content,
        summary=None,
    )


class KnowledgeGraphRetrievalNode(LLMUsageTrackingMixin, Node[KnowledgeGraphRetrievalNodeData]):
    """Retrieve tenant-scoped paths from standalone knowledge graph libraries."""

    node_type = KNOWLEDGE_GRAPH_RETRIEVAL_NODE_TYPE

    def __init__(
        self,
        node_id: str,
        data: KnowledgeGraphRetrievalNodeData,
        *,
        graph_init_params: "GraphInitParams",
        graph_runtime_state: "GraphRuntimeState",
    ) -> None:
        super().__init__(
            node_id=node_id,
            data=data,
            graph_init_params=graph_init_params,
            graph_runtime_state=graph_runtime_state,
        )
        self._knowledge_graph_service = KnowledgeGraphService()

    @classmethod
    def version(cls) -> str:
        return "1"

    def _run(self) -> NodeRunResult:
        usage = LLMUsage.empty_usage()
        variables: dict[str, Any] = {}
        if not self._node_data.query_variable_selector:
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.SUCCEEDED,
                inputs={},
                process_data={},
                outputs={},
                metadata={},
                llm_usage=usage,
            )

        variable = self.graph_runtime_state.variable_pool.get(self._node_data.query_variable_selector)
        if not isinstance(variable, StringSegment):
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs={},
                error="Query variable is not string type.",
                llm_usage=usage,
            )

        variables["query"] = variable.value
        try:
            sources = self._retrieve_graph_sources(query=variable.value)
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.SUCCEEDED,
                inputs=variables,
                process_data={"usage": usage.model_dump()},
                outputs={
                    "result": ArrayObjectSegment(
                        value=[jsonable_encoder(item.model_dump(by_alias=True)) for item in sources],
                    ),
                },
                metadata={},
                llm_usage=usage,
            )
        except Exception as e:
            logger.warning("Error when running knowledge graph retrieval node", exc_info=True)
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs=variables,
                error=str(e),
                error_type=type(e).__name__,
                llm_usage=usage,
            )

    def _retrieve_graph_sources(self, query: str) -> list[Source]:
        """Fetch graph results for this node and convert them for workflow outputs."""
        dify_ctx = DifyRunContext.model_validate(self.require_run_context_value(DIFY_RUN_CONTEXT_KEY))
        graph_results = self._knowledge_graph_service.retrieve(
            GraphRetrievalRequest(
                tenant_id=dify_ctx.tenant_id,
                graph_ids=self._node_data.graph_ids,
                query=query,
                top_k=self._node_data.top_k,
                retrieval_config=self._node_data.retrieval_config,
            )
        )
        return [graph_result_to_source(result) for result in graph_results]

    @classmethod
    def _extract_variable_selector_to_variable_mapping(
        cls,
        *,
        graph_config: Mapping[str, Any],
        node_id: str,
        node_data: KnowledgeGraphRetrievalNodeData,
    ) -> Mapping[str, Sequence[str]]:
        _ = graph_config
        if node_data.query_variable_selector:
            return {node_id + ".query": node_data.query_variable_selector}
        return {}
