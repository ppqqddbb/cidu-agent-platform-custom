"""Workflow node that combines dataset retrieval with standalone graph retrieval."""

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from core.app.entities.app_invoke_entities import DIFY_RUN_CONTEXT_KEY, DifyRunContext
from core.knowledge_graph.entities import GraphRetrievalRequest
from core.workflow.nodes.knowledge_graph_retrieval.entities import HYBRID_RETRIEVAL_NODE_TYPE
from core.workflow.nodes.knowledge_graph_retrieval.knowledge_graph_retrieval_node import graph_result_to_source
from core.workflow.nodes.knowledge_retrieval.exc import KnowledgeRetrievalNodeError, RateLimitExceededError
from core.workflow.nodes.knowledge_retrieval.knowledge_retrieval_node import KnowledgeRetrievalNode
from core.workflow.nodes.knowledge_retrieval.retrieval import Source
from graphon.enums import WorkflowNodeExecutionMetadataKey, WorkflowNodeExecutionStatus
from graphon.model_runtime.entities.llm_entities import LLMUsage
from graphon.model_runtime.utils.encoders import jsonable_encoder
from graphon.node_events import NodeRunResult
from graphon.nodes.base import LLMUsageTrackingMixin
from graphon.nodes.base.node import Node
from graphon.variables.segments import ArrayObjectSegment
from services.knowledge_graph_service import KnowledgeGraphService

from .entities import HybridRetrievalNodeData

if TYPE_CHECKING:
    from graphon.entities import GraphInitParams
    from graphon.runtime import GraphRuntimeState

logger = logging.getLogger(__name__)


class HybridRetrievalNode(LLMUsageTrackingMixin, Node[HybridRetrievalNodeData]):
    """Retrieve from datasets and graph libraries, then expose one workflow result list."""

    node_type = HYBRID_RETRIEVAL_NODE_TYPE

    def __init__(
        self,
        node_id: str,
        data: HybridRetrievalNodeData,
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
        variables_result = self._extract_query_and_attachments()
        usage = LLMUsage.empty_usage()
        if isinstance(variables_result, NodeRunResult):
            return variables_result

        variables = variables_result
        if not variables:
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.SUCCEEDED,
                inputs={},
                process_data={},
                outputs={},
                metadata={},
                llm_usage=usage,
            )

        try:
            dataset_sources, usage = self._fetch_dataset_sources(variables)
            graph_sources = self._fetch_graph_sources(query=variables.get("query"))
            # Preserve source-specific metadata on each item; downstream nodes only need one `result` variable.
            sources: list[Source] = [*dataset_sources, *graph_sources]
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.SUCCEEDED,
                inputs=variables,
                process_data={"usage": jsonable_encoder(usage)},
                outputs={
                    "result": ArrayObjectSegment(
                        value=[jsonable_encoder(item.model_dump(by_alias=True)) for item in sources],
                    ),
                },
                metadata={
                    WorkflowNodeExecutionMetadataKey.TOTAL_TOKENS: usage.total_tokens,
                    WorkflowNodeExecutionMetadataKey.TOTAL_PRICE: usage.total_price,
                    WorkflowNodeExecutionMetadataKey.CURRENCY: usage.currency,
                },
                llm_usage=usage,
            )
        except RateLimitExceededError as e:
            logger.warning(e, exc_info=True)
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs=variables,
                error=str(e),
                error_type=type(e).__name__,
                llm_usage=usage,
            )
        except KnowledgeRetrievalNodeError as e:
            logger.warning("Error when running hybrid retrieval node", exc_info=True)
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs=variables,
                error=str(e),
                error_type=type(e).__name__,
                llm_usage=usage,
            )
        except Exception as e:
            logger.warning("Unexpected error when running hybrid retrieval node", exc_info=True)
            return NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                inputs=variables,
                error=str(e),
                error_type=type(e).__name__,
                llm_usage=usage,
            )

    def _extract_query_and_attachments(self) -> dict[str, Any] | NodeRunResult:
        """Use the same query validation contract as the dataset retrieval node."""
        usage = LLMUsage.empty_usage()
        if not self._node_data.query_variable_selector and not self._node_data.query_attachment_selector:
            return {}

        from graphon.variables import ArrayFileSegment, FileSegment, StringSegment

        variables: dict[str, Any] = {}
        if self._node_data.query_variable_selector:
            variable = self.graph_runtime_state.variable_pool.get(self._node_data.query_variable_selector)
            if not isinstance(variable, StringSegment):
                return NodeRunResult(
                    status=WorkflowNodeExecutionStatus.FAILED,
                    inputs={},
                    error="Query variable is not string type.",
                    llm_usage=usage,
                )
            variables["query"] = variable.value

        if self._node_data.query_attachment_selector:
            variable = self.graph_runtime_state.variable_pool.get(self._node_data.query_attachment_selector)
            if not isinstance(variable, ArrayFileSegment) and not isinstance(variable, FileSegment):
                return NodeRunResult(
                    status=WorkflowNodeExecutionStatus.FAILED,
                    inputs={},
                    error="Attachments variable is not array file or file type.",
                    llm_usage=usage,
                )
            variables["attachments"] = variable.value if isinstance(variable, ArrayFileSegment) else [variable.value]

        return variables

    def _fetch_dataset_sources(self, variables: dict[str, Any]) -> tuple[list[Source], LLMUsage]:
        if not self._node_data.dataset_ids:
            return [], LLMUsage.empty_usage()

        # Reuse the existing knowledge-base retrieval implementation so hybrid retrieval keeps dataset behavior intact.
        helper = KnowledgeRetrievalNode(
            node_id=self.id,
            data=self._node_data,
            graph_init_params=self.graph_init_params,
            graph_runtime_state=self.graph_runtime_state,
        )
        return helper._fetch_dataset_retriever(self._node_data, variables)

    def _fetch_graph_sources(self, query: str | None) -> list[Source]:
        node_data = self.node_data
        if not query or not node_data.graph_ids:
            return []

        dify_ctx = DifyRunContext.model_validate(self.require_run_context_value(DIFY_RUN_CONTEXT_KEY))
        graph_results = self._knowledge_graph_service.retrieve(
            GraphRetrievalRequest(
                tenant_id=dify_ctx.tenant_id,
                graph_ids=node_data.graph_ids,
                query=query,
                top_k=node_data.graph_top_k,
                retrieval_config=node_data.graph_retrieval_config,
            )
        )
        return [graph_result_to_source(result) for result in graph_results]

    @classmethod
    def _extract_variable_selector_to_variable_mapping(
        cls,
        *,
        graph_config: Mapping[str, Any],
        node_id: str,
        node_data: HybridRetrievalNodeData,
    ) -> Mapping[str, Sequence[str]]:
        _ = graph_config
        variable_mapping = {}
        if node_data.query_variable_selector:
            variable_mapping[node_id + ".query"] = node_data.query_variable_selector
        if node_data.query_attachment_selector:
            variable_mapping[node_id + ".queryAttachment"] = node_data.query_attachment_selector
        return variable_mapping
