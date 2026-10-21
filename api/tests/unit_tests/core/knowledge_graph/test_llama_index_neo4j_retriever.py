import pytest
from neo4j.time import DateTime

from core.knowledge_graph.entities import (
    GraphImportTemplate,
    GraphRetrievalConfig,
    GraphRetrievalRequest,
    GraphSyncTemplate,
)
from core.knowledge_graph.llama_index_neo4j_retriever import LlamaIndexNeo4jGraphRetriever


class FakeGraphStore:
    def __init__(self) -> None:
        self.query = ""
        self.params = {}

    def structured_query(self, query, param_map=None):
        self.query = query
        self.params = param_map or {}
        return [
            {
                "graph_id": "graph-a",
                "source_id": "dify",
                "source_name": "Dify",
                "relation_id": "rel-a",
                "relation_type": "USES",
                "target_id": "neo4j",
                "target_name": "Neo4j",
                "score": 1.0,
                "source_properties": {
                    "tenant_id": "tenant-a",
                    "graph_id": "graph-a",
                    "created_at": DateTime(2026, 5, 7, 3, 13, 17, 205000000),
                },
                "relation_properties": {},
                "target_properties": {"tenant_id": "tenant-a", "graph_id": "graph-a"},
            }
        ]

    def close(self):
        pass


def test_retrieve_enforces_tenant_and_graph_filters_in_cypher():
    graph_store = FakeGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)

    results = retriever.retrieve(
        GraphRetrievalRequest(
            tenant_id="tenant-a",
            graph_ids=["graph-a"],
            query="Neo4j",
            top_k=3,
            retrieval_config=GraphRetrievalConfig(strategy="path"),
        )
    )

    assert "source.tenant_id = $tenant_id" in graph_store.query
    assert "target.tenant_id = $tenant_id" in graph_store.query
    assert "source.graph_id IN $graph_ids" in graph_store.query
    assert "target.graph_id IN $graph_ids" in graph_store.query
    assert graph_store.params == {
        "tenant_id": "tenant-a",
        "graph_ids": ["graph-a"],
        "query": "neo4j",
        "query_tokens": ["neo4j"],
        "query_terms": ["neo4j"],
        "limit": 3,
    }
    assert results[0].content == "Dify USES Neo4j"
    assert results[0].metadata["source"]["created_at"] == "2026-05-07T03:13:17.205000000"
    assert results[0].metadata["source_id"] == "dify"
    assert results[0].metadata["relation_id"] == "rel-a"
    assert results[0].metadata["target_id"] == "neo4j"


def test_request_rejects_empty_graph_ids():
    with pytest.raises(ValueError):
        GraphRetrievalRequest(tenant_id="tenant-a", graph_ids=[], query="Neo4j")


def test_default_retrieval_config_targets_product_models_with_paths_and_parameters():
    config = GraphRetrievalConfig()

    assert config.strategy == "node"
    assert config.target_node_types == ["ProductModel"]
    assert config.include_paths is True
    assert config.path_depth == 8
    assert config.include_parameters is True
    assert config.deduplicate is True


class FakeNodeGraphStore:
    def __init__(self) -> None:
        self.query = ""
        self.params = {}

    def structured_query(self, query, param_map=None):
        self.query = query
        self.params = param_map or {}
        return [
            {
                "graph_id": "graph-a",
                "node_id": "model-a",
                "node_name": "钢板式管板双管圈中上部单双层单H翅片管管排",
                "node_type": "ProductModel",
                "node_description": "翅片管模型",
                "score": 1.03,
                "node_properties": {
                    "tenant_id": "tenant-a",
                    "graph_id": "graph-a",
                    "template_name": "钢板式管板双管圈中上部单双层单H翅片管管排.jyasm",
                },
                "ancestor_path": [
                    {"id": "root", "name": "3.环保设计", "type": "Catalog", "properties": {}},
                    {"id": "economizer", "name": "1.省煤器", "type": "Catalog", "properties": {}},
                    {
                        "id": "model-a",
                        "name": "钢板式管板双管圈中上部单双层单H翅片管管排",
                        "type": "ProductModel",
                        "properties": {},
                    },
                ],
                "parameters": [
                    {
                        "id": "height",
                        "name": "高度",
                        "type": "Parameter",
                        "relation_type": "DEFINES_PARAMETER",
                        "properties": {},
                    }
                ],
            },
            {
                "graph_id": "graph-a",
                "node_id": "model-a",
                "node_name": "钢板式管板双管圈中上部单双层单H翅片管管排",
                "node_type": "ProductModel",
                "node_description": "duplicate",
                "score": 0.9,
                "node_properties": {},
                "ancestor_path": [],
                "parameters": [],
            },
        ]

    def close(self):
        pass


def test_node_retrieval_uses_configurable_model_filter_paths_and_parameters():
    graph_store = FakeNodeGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)

    results = retriever.retrieve(
        GraphRetrievalRequest(
            tenant_id="tenant-a",
            graph_ids=["graph-a"],
            query="中部 翅片",
            top_k=5,
            retrieval_config=GraphRetrievalConfig(
                strategy="node",
                target_node_types=["ProductModel"],
                match_mode="all",
                include_paths=True,
                include_parameters=True,
                parameter_relation_types=["DEFINES_PARAMETER"],
                deduplicate=True,
            ),
        )
    )

    assert "coalesce(node.type, head(labels(node)), '') IN $target_node_types" in graph_store.query
    assert "all(token IN $query_terms WHERE search_text CONTAINS token)" in graph_store.query
    assert "OPTIONAL MATCH path=(ancestor)-[*1..8]->(node)" in graph_store.query
    assert "OPTIONAL MATCH (node)-[param_rel]->(parameter)" in graph_store.query
    assert graph_store.params["target_node_types"] == ["ProductModel"]
    assert graph_store.params["query_terms"] == ["中部", "翅片"]
    assert graph_store.params["parameter_relation_types"] == ["DEFINES_PARAMETER"]
    assert results[0].metadata["node_type"] == "ProductModel"
    assert (
        results[0].metadata["full_node_path"]
        == "3.环保设计/1.省煤器/钢板式管板双管圈中上部单双层单H翅片管管排/"
        "钢板式管板双管圈中上部单双层单H翅片管管排.jyasm"
    )
    assert results[0].metadata["node_path"] == "3.环保设计/1.省煤器/钢板式管板双管圈中上部单双层单H翅片管管排"
    assert (
        "full_node_path:3.环保设计/1.省煤器/钢板式管板双管圈中上部单双层单H翅片管管排/"
        "钢板式管板双管圈中上部单双层单H翅片管管排.jyasm"
    ) in results[0].content
    assert results[0].metadata["parameters"][0]["name"] == "高度"
    assert len(results) == 1


class FakeOverviewGraphStore:
    def __init__(self) -> None:
        self.queries = []
        self.params = []

    def structured_query(self, query, param_map=None):
        self.queries.append(query)
        self.params.append(param_map or {})
        if "MATCH (node)" in query:
            return [
                {
                    "node_count": 1,
                    "nodes": [
                        {
                            "id": "dify",
                            "name": "Dify",
                            "type": "Platform",
                            "description": "LLM app platform",
                            "labels": ["Entity"],
                            "properties": {
                                "tenant_id": "tenant-a",
                                "graph_id": "graph-a",
                                "created_at": DateTime(2026, 5, 7, 3, 13, 17, 205000000),
                            },
                        }
                    ],
                }
            ]
        return [
            {
                "relationship_count": 1,
                "relationships": [
                    {
                        "id": "rel-a",
                        "source_id": "dify",
                        "source_name": "Dify",
                        "relation_type": "USES",
                        "target_id": "neo4j",
                        "target_name": "Neo4j",
                        "confidence": 0.95,
                        "properties": {
                            "created_at": DateTime(2026, 5, 7, 3, 13, 17, 388000000),
                        },
                    }
                ],
            }
        ]

    def close(self):
        pass


def test_get_overview_enforces_tenant_and_graph_filters_and_serializes_values():
    graph_store = FakeOverviewGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)

    overview = retriever.get_overview(tenant_id="tenant-a", graph_id="graph-a", limit=20)

    assert "node.tenant_id = $tenant_id" in graph_store.queries[0]
    assert "node.graph_id = $graph_id" in graph_store.queries[0]
    assert "source.tenant_id = $tenant_id" in graph_store.queries[1]
    assert "target.tenant_id = $tenant_id" in graph_store.queries[1]
    assert graph_store.params == [
        {
            "tenant_id": "tenant-a",
            "graph_id": "graph-a",
            "limit": 20,
        },
        {
            "tenant_id": "tenant-a",
            "graph_id": "graph-a",
            "limit": 20,
        },
    ]
    assert overview.node_count == 1
    assert overview.relationship_count == 1
    assert overview.nodes[0].properties["created_at"] == "2026-05-07T03:13:17.205000000"
    assert overview.relationships[0].properties["created_at"] == "2026-05-07T03:13:17.388000000"


def test_get_overview_allows_large_node_limits():
    graph_store = FakeOverviewGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)

    retriever.get_overview(tenant_id="tenant-a", graph_id="graph-a", limit=1000)

    assert graph_store.params[0]["limit"] == 1000
    assert graph_store.params[1]["limit"] == 1000


class FakeImportGraphStore:
    def __init__(self) -> None:
        self.queries = []
        self.params = []

    def structured_query(self, query, param_map=None):
        self.queries.append(query)
        self.params.append(param_map or {})
        return []

    def close(self):
        pass


def test_import_template_upserts_tenant_scoped_nodes_and_relationships():
    graph_store = FakeImportGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)
    template = GraphImportTemplate(
        nodes=[
            {
                "id": "dify",
                "name": "Dify",
                "type": "Platform",
                "description": "LLM app platform",
                "properties": {"tenant_id": "ignored", "aliases": ["Dify.AI"]},
            },
            {
                "id": "neo4j",
                "name": "Neo4j",
                "type": "Database",
            },
        ],
        relationships=[
            {
                "source_id": "dify",
                "target_id": "neo4j",
                "relation_type": "USES",
                "confidence": 0.95,
                "properties": {"graph_id": "ignored", "source": {"file": "intro.md"}},
            }
        ],
    )

    result = retriever.import_template(tenant_id="tenant-a", graph_id="graph-a", template=template)

    assert result.node_count == 2
    assert result.relationship_count == 1
    assert "MERGE (entity:KnowledgeGraphEntity" in graph_store.queries[0]
    assert "tenant_id: $tenant_id" in graph_store.queries[0]
    assert "graph_id: $graph_id" in graph_store.queries[0]
    assert "MERGE (source)-[rel:KNOWLEDGE_GRAPH_RELATION" in graph_store.queries[1]
    assert "USES" not in graph_store.queries[1]
    assert graph_store.params[0]["tenant_id"] == "tenant-a"
    assert graph_store.params[0]["graph_id"] == "graph-a"
    assert graph_store.params[0]["nodes"][0]["properties"] == {"aliases": ["Dify.AI"]}
    assert graph_store.params[1]["relationships"][0]["relation_type"] == "USES"
    assert graph_store.params[1]["relationships"][0]["properties"] == {"source": '{"file": "intro.md"}'}


def test_import_template_rejects_relationships_with_missing_nodes():
    with pytest.raises(ValueError, match="relationships reference missing node ids"):
        GraphImportTemplate(
            nodes=[{"id": "dify", "name": "Dify"}],
            relationships=[{"source_id": "dify", "target_id": "neo4j", "relation_type": "USES"}],
        )


class FakeSyncGraphStore:
    def __init__(self) -> None:
        self.queries = []
        self.params = []

    def structured_query(self, query, param_map=None):
        self.queries.append(query)
        self.params.append(param_map or {})
        if "DELETE rel" in query:
            return [{"deleted_count": 3}]
        if "DETACH DELETE node" in query:
            return [{"deleted_count": 2}]
        return []

    def close(self):
        pass


def test_sync_template_clears_existing_graph_before_bulk_import():
    graph_store = FakeSyncGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)
    template = GraphSyncTemplate(
        nodes=[
            {"id": "database:1", "name": "jiavusystemdata", "type": "Database", "key": "jiavusystemdata"},
            {"id": "table:1", "name": "product_model", "type": "Table", "key": "product_model"},
        ],
        edges=[
            {
                "source": "database:1",
                "target": "table:1",
                "type": "HAS_TABLE",
            }
        ],
    )

    result = retriever.sync_template(tenant_id="tenant-a", graph_id="graph-a", template=template)

    assert result.deleted_relationship_count == 3
    assert result.deleted_node_count == 2
    assert result.node_count == 2
    assert result.relationship_count == 1
    assert "DELETE rel" in graph_store.queries[0]
    assert "DETACH DELETE node" in graph_store.queries[1]
    assert "MERGE (entity:KnowledgeGraphEntity" in graph_store.queries[2]
    assert "MERGE (source)-[rel:KNOWLEDGE_GRAPH_RELATION" in graph_store.queries[3]
    assert graph_store.params[2]["nodes"][0]["properties"] == {"key": "jiavusystemdata"}
    assert graph_store.params[3]["relationships"][0]["relation_type"] == "HAS_TABLE"


def test_sync_template_can_upsert_without_clearing_existing_graph():
    graph_store = FakeSyncGraphStore()
    retriever = LlamaIndexNeo4jGraphRetriever(graph_store)
    template = GraphSyncTemplate(
        clear_existing=False,
        nodes=[{"id": "root", "name": "root"}],
    )

    result = retriever.sync_template(tenant_id="tenant-a", graph_id="graph-a", template=template)

    assert result.deleted_relationship_count == 0
    assert result.deleted_node_count == 0
    assert result.node_count == 1
    assert len(graph_store.queries) == 1
    assert "MERGE (entity:KnowledgeGraphEntity" in graph_store.queries[0]
