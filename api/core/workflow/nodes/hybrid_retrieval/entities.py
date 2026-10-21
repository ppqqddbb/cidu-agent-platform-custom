"""Data contracts for hybrid knowledge-base and graph retrieval nodes."""

from pydantic import Field, PositiveInt

from graphon.enums import NodeType

from core.knowledge_graph.entities import GraphRetrievalConfig
from core.workflow.nodes.knowledge_graph_retrieval.entities import HYBRID_RETRIEVAL_NODE_TYPE
from core.workflow.nodes.knowledge_retrieval.entities import KnowledgeRetrievalNodeData


class HybridRetrievalNodeData(KnowledgeRetrievalNodeData):
    """
    Hybrid retrieval node data.

    Dataset and graph library selections stay explicit so the workflow can retrieve from both resources while keeping
    their management surfaces independent.
    """

    type: NodeType = HYBRID_RETRIEVAL_NODE_TYPE
    graph_ids: list[str] = Field(default_factory=list)
    graph_top_k: PositiveInt | None = None
    graph_retrieval_config: GraphRetrievalConfig = Field(default_factory=GraphRetrievalConfig)
