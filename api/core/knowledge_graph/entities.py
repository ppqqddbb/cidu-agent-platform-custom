import json
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

_NODE_RESERVED_PROPERTIES = {"tenant_id", "graph_id", "id", "name", "type", "description", "labels"}
_RELATIONSHIP_RESERVED_PROPERTIES = {
    "tenant_id",
    "graph_id",
    "id",
    "relation_type",
    "confidence",
}


def _sanitize_properties(properties: dict[str, Any], reserved_keys: set[str]) -> dict[str, Any]:
    return {
        str(key): _to_neo4j_property_value(value)
        for key, value in properties.items()
        if str(key) not in reserved_keys and value is not None
    }


def _to_neo4j_property_value(value: Any) -> str | int | float | bool | list[str | int | float | bool]:
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list) and all(isinstance(item, str | int | float | bool) for item in value):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class GraphRetrievalConfig(BaseModel):
    """User-controlled options for graph retrieval behavior."""

    strategy: Literal["path", "node"] = Field(default="node", description="Retrieval strategy")
    target_node_types: list[str] = Field(
        default_factory=lambda: ["ProductModel"],
        description="Node types to return in node strategy",
    )
    match_mode: Literal["any", "all"] = Field(default="any", description="Token matching mode")
    include_paths: bool = Field(default=True, description="Whether to include ancestor paths for node hits")
    path_depth: PositiveInt = Field(default=8, description="Maximum ancestor path depth")
    include_parameters: bool = Field(default=True, description="Whether to include parameter neighbors for node hits")
    parameter_relation_types: list[str] = Field(
        default_factory=lambda: ["DEFINES_PARAMETER"],
        description="Relationship types used to collect parameter neighbors",
    )
    deduplicate: bool = Field(default=True, description="Whether to collapse duplicate graph hits")

    model_config = ConfigDict(extra="forbid")

    @field_validator("target_node_types", "parameter_relation_types")
    @classmethod
    def validate_text_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("path_depth")
    @classmethod
    def validate_path_depth(cls, value: int) -> int:
        return min(max(value, 1), 8)


class GraphRetrievalRequest(BaseModel):
    """Input contract for retrieving from standalone tenant-scoped knowledge graphs."""

    tenant_id: str = Field(description="Tenant unique identifier")
    graph_ids: list[str] = Field(description="Standalone knowledge graph IDs to retrieve from")
    query: str = Field(description="User query text")
    top_k: PositiveInt | None = Field(default=None, description="Maximum number of graph results to return")
    retrieval_config: GraphRetrievalConfig = Field(default_factory=GraphRetrievalConfig)

    model_config = ConfigDict(extra="forbid")

    @field_validator("tenant_id", "query")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value

    @field_validator("graph_ids")
    @classmethod
    def validate_graph_ids(cls, value: list[str]) -> list[str]:
        graph_ids = [graph_id.strip() for graph_id in value if graph_id.strip()]
        if not graph_ids:
            raise ValueError("graph_ids cannot be empty")
        return graph_ids


class GraphRetrievalResult(BaseModel):
    """
    A retrieval hit from the standalone graph subsystem.

    This is deliberately not `Source`: graph results are a separate resource type. Hybrid retrieval can adapt these into
    the prompt context later, after it has decided how to rank graph hits against knowledge-base hits.
    """

    graph_id: str = Field(description="Standalone knowledge graph ID")
    title: str = Field(description="Human-readable result title")
    content: str = Field(description="Textual representation of the matched graph path")
    score: float = Field(default=0.0, description="Simple relevance score assigned by the graph retriever")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Raw graph metadata useful for tracing")

    model_config = ConfigDict(extra="forbid")


class GraphOverviewNode(BaseModel):
    """A tenant-scoped Neo4j node prepared for the console graph detail page."""

    id: str = Field(description="Stable node identifier or Neo4j internal identifier")
    name: str = Field(description="Human-readable node name")
    type: str = Field(default="", description="Domain node type")
    description: str = Field(default="", description="Node description")
    labels: list[str] = Field(default_factory=list, description="Neo4j labels attached to the node")
    properties: dict[str, Any] = Field(default_factory=dict, description="JSON-safe node properties")

    model_config = ConfigDict(extra="forbid")


class GraphOverviewRelationship(BaseModel):
    """A tenant-scoped Neo4j relationship prepared for the console graph detail page."""

    id: str = Field(description="Stable relationship identifier or Neo4j internal identifier")
    source_id: str = Field(description="Stable source node identifier")
    source_name: str = Field(description="Relationship source node display name")
    relation_type: str = Field(description="Neo4j relationship type")
    target_id: str = Field(description="Stable target node identifier")
    target_name: str = Field(description="Relationship target node display name")
    confidence: float = Field(default=0.0, description="Optional relation confidence")
    properties: dict[str, Any] = Field(default_factory=dict, description="JSON-safe relationship properties")

    model_config = ConfigDict(extra="forbid")


class GraphOverview(BaseModel):
    """Default summary shown when opening a standalone knowledge graph library."""

    node_count: int = Field(default=0, ge=0, description="Total nodes in the graph library")
    relationship_count: int = Field(default=0, ge=0, description="Total relationships in the graph library")
    nodes: list[GraphOverviewNode] = Field(default_factory=list, description="Sample nodes for display")
    relationships: list[GraphOverviewRelationship] = Field(
        default_factory=list,
        description="Sample relationships for display",
    )

    model_config = ConfigDict(extra="forbid")


class GraphImportNode(BaseModel):
    """A node from the structured knowledge graph import template."""

    id: str = Field(description="Stable node identifier within the graph template")
    name: str = Field(description="Human-readable node name")
    type: str = Field(default="", description="Domain node type")
    description: str = Field(default="", description="Node description")
    labels: list[str] = Field(default_factory=list, max_length=20, description="Optional display labels")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional JSON-safe node properties")

    model_config = ConfigDict(extra="forbid")

    @field_validator("id", "name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        if len(value) > 120:
            raise ValueError("value cannot exceed 120 characters")
        return value

    @field_validator("type", "description")
    @classmethod
    def validate_optional_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) > 400:
            raise ValueError("value cannot exceed 400 characters")
        return value

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: list[str]) -> list[str]:
        labels = []
        for label in value:
            label = label.strip()
            if label:
                labels.append(label[:80])
        return labels

    def to_import_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "labels": self.labels,
            "properties": _sanitize_properties(self.properties, _NODE_RESERVED_PROPERTIES),
        }


class GraphImportRelationship(BaseModel):
    """A directed relationship from the structured knowledge graph import template."""

    id: str | None = Field(default=None, description="Stable relationship identifier; generated when omitted")
    source_id: str = Field(description="Source node identifier from the same import template")
    target_id: str = Field(description="Target node identifier from the same import template")
    relation_type: str = Field(description="Human-readable relationship type")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Optional extraction confidence")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional JSON-safe relationship properties")

    model_config = ConfigDict(extra="forbid")

    @field_validator("id")
    @classmethod
    def validate_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 160:
            raise ValueError("relationship id cannot exceed 160 characters")
        return value

    @field_validator("source_id", "target_id", "relation_type")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        if len(value) > 120:
            raise ValueError("value cannot exceed 120 characters")
        return value

    def stable_id(self) -> str:
        if self.id:
            return self.id
        raw_id = f"{self.source_id}|{self.relation_type}|{self.target_id}"
        return f"rel-{sha256(raw_id.encode()).hexdigest()[:32]}"

    def to_import_record(self) -> dict[str, Any]:
        return {
            "id": self.stable_id(),
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "properties": _sanitize_properties(self.properties, _RELATIONSHIP_RESERVED_PROPERTIES),
        }


class GraphImportTemplate(BaseModel):
    """
    Structured import template accepted by the console knowledge graph import API.

    The template is intentionally self-contained: relationships must reference nodes in the same payload. Tooling that
    extracts entities from files or free text can target this shape and then call the same import endpoint.
    """

    nodes: list[GraphImportNode] = Field(min_length=1, max_length=1000, description="Nodes to upsert")
    relationships: list[GraphImportRelationship] = Field(
        default_factory=list,
        max_length=2000,
        description="Directed relationships to upsert",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_relationship_nodes(self) -> "GraphImportTemplate":
        node_ids = [node.id for node in self.nodes]
        duplicate_node_ids = {node_id for node_id in node_ids if node_ids.count(node_id) > 1}
        if duplicate_node_ids:
            raise ValueError(f"duplicate node ids: {', '.join(sorted(duplicate_node_ids))}")

        node_id_set = set(node_ids)
        missing_node_ids = sorted(
            {
                node_id
                for relationship in self.relationships
                for node_id in (relationship.source_id, relationship.target_id)
                if node_id not in node_id_set
            }
        )
        if missing_node_ids:
            raise ValueError(f"relationships reference missing node ids: {', '.join(missing_node_ids)}")
        return self


class GraphImportResult(BaseModel):
    """Summary returned after importing a structured knowledge graph template."""

    node_count: int = Field(default=0, ge=0, description="Number of node records submitted to Neo4j")
    relationship_count: int = Field(default=0, ge=0, description="Number of relationship records submitted to Neo4j")

    model_config = ConfigDict(extra="forbid")


class GraphSyncTemplate(BaseModel):
    """
    Full graph template accepted by service API automation.

    Unlike `GraphImportTemplate`, this model is sized for production sync jobs and accepts the native JiaYu export
    shape (`edges` with `source`/`target`/`type`) as an input convenience. It still normalizes to the same import node
    and relationship records before Neo4j writes happen.
    """

    nodes: list[GraphImportNode] = Field(min_length=1, max_length=50000, description="Nodes to replace or upsert")
    relationships: list[GraphImportRelationship] = Field(
        default_factory=list,
        max_length=100000,
        description="Directed relationships to replace or upsert",
    )
    clear_existing: bool = Field(
        default=True,
        description="Whether to delete existing Neo4j content for the target graph before importing",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def normalize_native_export(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        nodes = normalized.get("nodes")
        if isinstance(nodes, list):
            normalized["nodes"] = [cls._normalize_native_node(node) for node in nodes]

        if "relationships" not in normalized and isinstance(normalized.get("edges"), list):
            normalized["relationships"] = [
                cls._normalize_native_edge(edge)
                for edge in normalized.get("edges", [])
                if isinstance(edge, dict)
            ]
            normalized.pop("edges", None)

        for metadata_key in ("schema_version", "source", "database", "generated_at"):
            normalized.pop(metadata_key, None)
        return normalized

    @model_validator(mode="after")
    def validate_relationship_nodes(self) -> "GraphSyncTemplate":
        node_ids = [node.id for node in self.nodes]
        duplicate_node_ids = {node_id for node_id in node_ids if node_ids.count(node_id) > 1}
        if duplicate_node_ids:
            raise ValueError(f"duplicate node ids: {', '.join(sorted(duplicate_node_ids))}")

        node_id_set = set(node_ids)
        missing_node_ids = sorted(
            {
                node_id
                for relationship in self.relationships
                for node_id in (relationship.source_id, relationship.target_id)
                if node_id not in node_id_set
            }
        )
        if missing_node_ids:
            raise ValueError(f"relationships reference missing node ids: {', '.join(missing_node_ids)}")
        return self

    @staticmethod
    def _normalize_native_node(value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        properties = dict(value.get("properties") or {})
        original_name = str(value.get("name") or value.get("id") or "")
        original_description = str(value.get("description", ""))
        for key in ("key", "database", "table", "source"):
            if key in value and key not in properties:
                properties[key] = value[key]
        if original_name and len(original_name) > 120 and "original_name" not in properties:
            properties["original_name"] = original_name
        if original_description and len(original_description) > 400 and "original_description" not in properties:
            properties["original_description"] = original_description

        return {
            "id": value.get("id"),
            "name": original_name[:120],
            "type": str(value.get("type", ""))[:400],
            "description": original_description[:400],
            "labels": value.get("labels", []),
            "properties": properties,
        }

    @staticmethod
    def _normalize_native_edge(value: dict[str, Any]) -> dict[str, Any]:
        properties = dict(value.get("properties") or {})
        return {
            "id": value.get("id"),
            "source_id": value.get("source_id") or value.get("source"),
            "target_id": value.get("target_id") or value.get("target"),
            "relation_type": value.get("relation_type") or value.get("type"),
            "confidence": value.get("confidence", 1.0),
            "properties": properties,
        }


class GraphSyncResult(BaseModel):
    """Summary returned after a service API graph sync."""

    node_count: int = Field(default=0, ge=0, description="Number of node records submitted to Neo4j")
    relationship_count: int = Field(default=0, ge=0, description="Number of relationship records submitted to Neo4j")
    deleted_node_count: int = Field(default=0, ge=0, description="Number of nodes removed before import")
    deleted_relationship_count: int = Field(
        default=0,
        ge=0,
        description="Number of relationships removed before import",
    )

    model_config = ConfigDict(extra="forbid")
