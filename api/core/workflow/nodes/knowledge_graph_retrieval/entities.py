"""Data contracts for workflow-local knowledge graph retrieval nodes."""

from pydantic import Field, PositiveInt

from graphon.entities.base_node_data import BaseNodeData
from graphon.enums import NodeType

from core.knowledge_graph.entities import GraphRetrievalConfig

KNOWLEDGE_GRAPH_RETRIEVAL_NODE_TYPE: NodeType = "knowledge-graph-retrieval"
HYBRID_RETRIEVAL_NODE_TYPE: NodeType = "hybrid-retrieval"


class KnowledgeGraphRetrievalConfig(BaseNodeData):
    """
    Shared config for standalone graph retrieval inside workflow nodes.

    Graph libraries remain separate resources from Dify datasets. These fields only select
    which tenant-scoped graph libraries a node can query at runtime.
    """

    query_variable_selector: list[str] | None | str = None
    graph_ids: list[str] = Field(default_factory=list)
    top_k: PositiveInt | None = None
    retrieval_config: GraphRetrievalConfig = Field(default_factory=GraphRetrievalConfig)


class KnowledgeGraphRetrievalNodeData(KnowledgeGraphRetrievalConfig):
    """Knowledge graph retrieval node data."""

    type: NodeType = KNOWLEDGE_GRAPH_RETRIEVAL_NODE_TYPE
