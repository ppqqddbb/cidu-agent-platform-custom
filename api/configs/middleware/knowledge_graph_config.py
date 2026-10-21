from pydantic import Field, NonNegativeFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings


class KnowledgeGraphConfig(BaseSettings):
    """
    Settings for the standalone knowledge graph subsystem.

    The graph store is intentionally configured separately from vector stores and Dify datasets. Hybrid retrieval should
    combine knowledge-base and graph results in an orchestration layer instead of making either resource own the other.
    """

    KNOWLEDGE_GRAPH_ENABLED: bool = Field(
        description="Whether standalone knowledge graph retrieval is enabled.",
        default=False,
    )

    NEO4J_URI: str | None = Field(
        description="Bolt URI for the Neo4j database used by knowledge graph retrieval.",
        default=None,
    )

    NEO4J_USER: str | None = Field(
        description="Username for the Neo4j database used by knowledge graph retrieval.",
        default=None,
    )

    NEO4J_PASSWORD: SecretStr | None = Field(
        description="Password for the Neo4j database used by knowledge graph retrieval.",
        default=None,
    )

    NEO4J_DATABASE: str = Field(
        description="Neo4j database name for knowledge graph retrieval.",
        default="neo4j",
    )

    NEO4J_REFRESH_SCHEMA: bool = Field(
        description="Whether LlamaIndex should refresh the Neo4j graph schema when creating the graph store.",
        default=False,
    )

    NEO4J_TIMEOUT: NonNegativeFloat | None = Field(
        description="Timeout in seconds for Neo4j transactions. Set to 0 or leave empty to use the driver default.",
        default=None,
    )

    KNOWLEDGE_GRAPH_RETRIEVAL_TOP_K: PositiveInt = Field(
        description="Default number of graph retrieval results to return.",
        default=5,
    )
