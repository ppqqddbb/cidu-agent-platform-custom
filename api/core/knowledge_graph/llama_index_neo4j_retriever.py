"""
Neo4j-backed graph retrieval through LlamaIndex.

The first implementation intentionally uses a tenant-scoped Cypher template executed through LlamaIndex's
`Neo4jPropertyGraphStore`. Natural-language-to-Cypher can be added later, but generated Cypher must still pass through a
validator that injects or verifies `tenant_id` and `graph_id` predicates before execution.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, cast

from configs import dify_config

from .entities import (
    GraphImportResult,
    GraphImportTemplate,
    GraphOverview,
    GraphOverviewNode,
    GraphOverviewRelationship,
    GraphRetrievalConfig,
    GraphRetrievalRequest,
    GraphRetrievalResult,
    GraphSyncResult,
    GraphSyncTemplate,
)


class KnowledgeGraphConfigError(ValueError):
    """Raised when standalone knowledge graph retrieval is requested but Neo4j is not configured."""


class Neo4jGraphStoreProtocol(Protocol):
    """Subset of LlamaIndex Neo4jPropertyGraphStore used by this retriever."""

    def structured_query(self, query: str, param_map: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


class LlamaIndexNeo4jGraphRetriever:
    """
    Retrieves tenant-scoped paths from Neo4j using LlamaIndex's Neo4j property graph store.

    Graph data must carry `tenant_id` and `graph_id` on both endpoint nodes. Relationship properties may also carry the
    same identifiers, but node predicates are the hard isolation boundary because every returned path is anchored there.
    """

    _graph_store: Neo4jGraphStoreProtocol | None

    def __init__(self, graph_store: Neo4jGraphStoreProtocol | None = None) -> None:
        self._graph_store = graph_store

    def retrieve(self, request: GraphRetrievalRequest) -> list[GraphRetrievalResult]:
        graph_store = self._graph_store or self._create_graph_store()
        top_k = request.top_k or dify_config.KNOWLEDGE_GRAPH_RETRIEVAL_TOP_K
        query_tokens = self._query_tokens(request.query)
        query_terms = self._query_terms(request.query)
        retrieval_config = request.retrieval_config
        if retrieval_config.strategy == "node":
            rows = graph_store.structured_query(
                self._tenant_scoped_node_query(retrieval_config),
                param_map={
                    "tenant_id": request.tenant_id,
                    "graph_ids": request.graph_ids,
                    "query": request.query.lower(),
                    "query_tokens": query_tokens,
                    "query_terms": query_terms,
                    "target_node_types": retrieval_config.target_node_types,
                    "parameter_relation_types": retrieval_config.parameter_relation_types,
                    "limit": top_k,
                },
            )
            if retrieval_config.deduplicate:
                rows = self._deduplicate_rows(rows, "node_id")
            return [self._node_row_to_result(row) for row in rows]

        rows = graph_store.structured_query(
            self._tenant_scoped_path_query(),
            param_map={
                "tenant_id": request.tenant_id,
                "graph_ids": request.graph_ids,
                "query": request.query.lower(),
                "query_tokens": query_tokens,
                "query_terms": query_terms,
                "limit": top_k,
            },
        )
        if retrieval_config.deduplicate:
            rows = self._deduplicate_rows(rows, "relation_id")
        return [self._row_to_result(row) for row in rows]

    def get_overview(self, tenant_id: str, graph_id: str, limit: int = 50) -> GraphOverview:
        """
        Return a lightweight graph sample for the console detail page.

        The two Cypher queries intentionally repeat tenant and graph predicates. This keeps the default page view under
        the same isolation rules as search, even if future relationship properties drift from node properties.
        """
        graph_store = self._graph_store or self._create_graph_store()
        safe_limit = max(1, limit)
        node_rows = graph_store.structured_query(
            self._tenant_scoped_nodes_query(),
            param_map={
                "tenant_id": tenant_id,
                "graph_id": graph_id,
                "limit": safe_limit,
            },
        )
        relationship_rows = graph_store.structured_query(
            self._tenant_scoped_relationships_query(),
            param_map={
                "tenant_id": tenant_id,
                "graph_id": graph_id,
                "limit": safe_limit,
            },
        )
        node_row = node_rows[0] if node_rows else {}
        relationship_row = relationship_rows[0] if relationship_rows else {}
        nodes = [
            self._row_to_overview_node(node)
            for node in self._json_safe_value(node_row.get("nodes") or [])
            if isinstance(node, dict)
        ]
        relationships = [
            self._row_to_overview_relationship(relationship)
            for relationship in self._json_safe_value(relationship_row.get("relationships") or [])
            if isinstance(relationship, dict)
        ]
        return GraphOverview(
            node_count=int(node_row.get("node_count") or 0),
            relationship_count=int(relationship_row.get("relationship_count") or 0),
            nodes=nodes,
            relationships=relationships,
        )

    def import_template(self, tenant_id: str, graph_id: str, template: GraphImportTemplate) -> GraphImportResult:
        """
        Upsert a validated graph import template into Neo4j.

        Relationships use a fixed Neo4j type and store the template's relation name in `relation_type`. Cypher cannot
        parameterize relationship types safely, and this fixed type keeps user-provided template data out of query text.
        """
        graph_store = self._graph_store or self._create_graph_store()
        nodes = [node.to_import_record() for node in template.nodes]
        relationships = [relationship.to_import_record() for relationship in template.relationships]
        graph_store.structured_query(
            self._tenant_scoped_import_nodes_query(),
            param_map={
                "tenant_id": tenant_id,
                "graph_id": graph_id,
                "nodes": nodes,
            },
        )
        if relationships:
            graph_store.structured_query(
                self._tenant_scoped_import_relationships_query(),
                param_map={
                    "tenant_id": tenant_id,
                    "graph_id": graph_id,
                    "relationships": relationships,
                },
            )
        return GraphImportResult(node_count=len(nodes), relationship_count=len(relationships))

    def clear_graph(self, tenant_id: str, graph_id: str) -> GraphSyncResult:
        """Delete all Neo4j content for one tenant-scoped graph and return the removed counts."""
        graph_store = self._graph_store or self._create_graph_store()
        relationship_rows = graph_store.structured_query(
            self._tenant_scoped_delete_relationships_query(),
            param_map={
                "tenant_id": tenant_id,
                "graph_id": graph_id,
            },
        )
        node_rows = graph_store.structured_query(
            self._tenant_scoped_delete_nodes_query(),
            param_map={
                "tenant_id": tenant_id,
                "graph_id": graph_id,
            },
        )
        relationship_count = int((relationship_rows[0] if relationship_rows else {}).get("deleted_count") or 0)
        node_count = int((node_rows[0] if node_rows else {}).get("deleted_count") or 0)
        return GraphSyncResult(
            deleted_node_count=node_count,
            deleted_relationship_count=relationship_count,
        )

    def sync_template(self, tenant_id: str, graph_id: str, template: GraphSyncTemplate) -> GraphSyncResult:
        """
        Replace or upsert a full graph template for service API automation.

        The console import endpoint remains limited to small self-contained templates. This path is deliberately larger
        and imports nodes before relationships so callers can send an entire exported graph in one request.
        """
        deleted = GraphSyncResult()
        if template.clear_existing:
            deleted = self.clear_graph(tenant_id=tenant_id, graph_id=graph_id)

        graph_store = self._graph_store or self._create_graph_store()
        nodes = [node.to_import_record() for node in template.nodes]
        relationships = [relationship.to_import_record() for relationship in template.relationships]
        graph_store.structured_query(
            self._tenant_scoped_import_nodes_query(),
            param_map={
                "tenant_id": tenant_id,
                "graph_id": graph_id,
                "nodes": nodes,
            },
        )
        if relationships:
            graph_store.structured_query(
                self._tenant_scoped_import_relationships_query(),
                param_map={
                    "tenant_id": tenant_id,
                    "graph_id": graph_id,
                    "relationships": relationships,
                },
            )
        return GraphSyncResult(
            node_count=len(nodes),
            relationship_count=len(relationships),
            deleted_node_count=deleted.deleted_node_count,
            deleted_relationship_count=deleted.deleted_relationship_count,
        )

    def close(self) -> None:
        if self._graph_store:
            self._graph_store.close()

    @staticmethod
    def _create_graph_store() -> Neo4jGraphStoreProtocol:
        if not dify_config.KNOWLEDGE_GRAPH_ENABLED:
            raise KnowledgeGraphConfigError("knowledge graph retrieval is disabled")
        if not dify_config.NEO4J_URI or not dify_config.NEO4J_USER or dify_config.NEO4J_PASSWORD is None:
            raise KnowledgeGraphConfigError("NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD are required")

        try:
            from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
        except ImportError as exc:
            raise KnowledgeGraphConfigError(
                "llama-index-graph-stores-neo4j is required for knowledge graph retrieval"
            ) from exc

        timeout = dify_config.NEO4J_TIMEOUT if dify_config.NEO4J_TIMEOUT and dify_config.NEO4J_TIMEOUT > 0 else None
        return cast(
            Neo4jGraphStoreProtocol,
            Neo4jPropertyGraphStore(
                username=dify_config.NEO4J_USER,
                password=dify_config.NEO4J_PASSWORD.get_secret_value(),
                url=dify_config.NEO4J_URI,
                database=dify_config.NEO4J_DATABASE,
                refresh_schema=dify_config.NEO4J_REFRESH_SCHEMA,
                timeout=timeout,
            ),
        )

    @staticmethod
    def _tenant_scoped_path_query() -> str:
        # Keep graph and tenant predicates in the fixed template. User text is passed only as a Cypher parameter.
        return """
        MATCH p=(source)-[rel]->(target)
        WHERE source.tenant_id = $tenant_id
          AND target.tenant_id = $tenant_id
          AND source.graph_id IN $graph_ids
          AND target.graph_id IN $graph_ids
          AND (
            toLower(coalesce(source.name, '')) CONTAINS $query
            OR toLower(coalesce(source.description, '')) CONTAINS $query
            OR toLower(coalesce(target.name, '')) CONTAINS $query
            OR toLower(coalesce(target.description, '')) CONTAINS $query
            OR toLower(coalesce(rel.relation_type, type(rel))) CONTAINS $query
            OR any(token IN $query_tokens WHERE
              toLower(coalesce(source.name, '')) CONTAINS token
              OR toLower(coalesce(source.description, '')) CONTAINS token
              OR toLower(coalesce(target.name, '')) CONTAINS token
              OR toLower(coalesce(target.description, '')) CONTAINS token
              OR toLower(coalesce(rel.relation_type, type(rel))) CONTAINS token
            )
          )
        WITH source, rel, target, p,
             CASE
               WHEN toLower(coalesce(source.name, '')) = $query THEN 1.0
               WHEN toLower(coalesce(target.name, '')) = $query THEN 1.0
               ELSE 0.5 + 0.05 * size([
                 token IN $query_tokens WHERE
                 toLower(coalesce(source.name, '')) CONTAINS token
                 OR toLower(coalesce(source.description, '')) CONTAINS token
                 OR toLower(coalesce(target.name, '')) CONTAINS token
                 OR toLower(coalesce(target.description, '')) CONTAINS token
                 OR toLower(coalesce(rel.relation_type, type(rel))) CONTAINS token
               ])
             END AS score
        RETURN coalesce(source.graph_id, target.graph_id) AS graph_id,
               coalesce(source.id, toString(id(source))) AS source_id,
               coalesce(source.name, source.id, '') AS source_name,
               coalesce(rel.id, toString(id(rel))) AS relation_id,
               coalesce(rel.relation_type, type(rel)) AS relation_type,
               coalesce(target.id, toString(id(target))) AS target_id,
               coalesce(target.name, target.id, '') AS target_name,
               score AS score,
               properties(source) AS source_properties,
               properties(rel) AS relation_properties,
               properties(target) AS target_properties
        ORDER BY score DESC
        LIMIT toInteger($limit)
        """

    @staticmethod
    def _tenant_scoped_node_query(config: GraphRetrievalConfig) -> str:
        node_type_predicate = ""
        if config.target_node_types:
            node_type_predicate = "AND coalesce(node.type, head(labels(node)), '') IN $target_node_types"
        token_predicate = "any(token IN $query_tokens WHERE search_text CONTAINS token)"
        if config.match_mode == "all":
            token_predicate = "all(token IN $query_terms WHERE search_text CONTAINS token)"
        path_clause = """
        WITH node, [] AS ancestor_path, '' AS ancestor_search_text
        """
        path_return = "[] AS ancestor_path,"
        if config.include_paths:
            path_depth = min(max(config.path_depth, 1), 8)
            path_clause = f"""
        OPTIONAL MATCH path=(ancestor)-[*1..{path_depth}]->(node)
        WHERE ancestor.tenant_id = $tenant_id
          AND ancestor.graph_id IN $graph_ids
        WITH node,
             CASE
               WHEN path IS NULL THEN []
               ELSE nodes(path)
             END AS path_nodes
        WITH node,
             CASE
               WHEN size(path_nodes) = 0 THEN []
               ELSE [path_node IN path_nodes | {{
                 id: coalesce(path_node.id, toString(id(path_node))),
                 name: coalesce(path_node.name, path_node.id, ''),
                 type: coalesce(path_node.type, head(labels(path_node)), ''),
                 properties: properties(path_node)
               }}]
             END AS path_entry,
             CASE
               WHEN size(path_nodes) = 0 THEN ''
               ELSE reduce(path_text = '', path_node IN path_nodes |
                 path_text + ' ' +
                 coalesce(path_node.name, '') + ' ' +
                 coalesce(path_node.description, '') + ' ' +
                 coalesce(path_node.id, '') + ' ' +
                 coalesce(path_node.path, '') + ' ' +
                 coalesce(path_node.full_node_path, '')
               )
             END AS path_search_text
        ORDER BY size(path_entry) DESC
        WITH node, collect(path_entry)[0] AS ancestor_path, collect(path_search_text)[0] AS ancestor_search_text
        """
            path_return = "ancestor_path AS ancestor_path,"
        parameter_clause = ""
        parameter_return = "[] AS parameters"
        if config.include_parameters:
            parameter_clause = """
        OPTIONAL MATCH (node)-[param_rel]->(parameter)
        WHERE parameter.tenant_id = $tenant_id
          AND parameter.graph_id IN $graph_ids
          AND coalesce(param_rel.relation_type, type(param_rel)) IN $parameter_relation_types
        WITH node, search_text, score, ancestor_path,
             collect(CASE
               WHEN parameter IS NULL THEN null
               ELSE {
                 id: coalesce(parameter.id, toString(id(parameter))),
                 name: coalesce(parameter.name, parameter.id, ''),
                 type: coalesce(parameter.type, head(labels(parameter)), ''),
                 relation_type: coalesce(param_rel.relation_type, type(param_rel)),
                 properties: properties(parameter)
               }
             END) AS collected_parameters
        WITH node, search_text, score, ancestor_path,
             [parameter IN collected_parameters WHERE parameter IS NOT NULL] AS parameters
        """
            parameter_return = "parameters AS parameters"
        return f"""
        MATCH (node)
        WHERE node.tenant_id = $tenant_id
          AND node.graph_id IN $graph_ids
          {node_type_predicate}
        {path_clause}
        WITH node,
             ancestor_path,
             toLower(
               coalesce(node.name, '') + ' ' +
               coalesce(node.description, '') + ' ' +
               coalesce(node.id, '') + ' ' +
               coalesce(node.template_name, '') + ' ' +
               coalesce(node.template, '') + ' ' +
               coalesce(node.path, '') + ' ' +
               coalesce(node.full_node_path, '') + ' ' +
               coalesce(ancestor_search_text, '')
             ) AS search_text
        WHERE search_text CONTAINS $query
          OR ({token_predicate})
        WITH node, search_text, ancestor_path,
             CASE
               WHEN toLower(coalesce(node.name, '')) = $query THEN 1.0
               WHEN toLower(coalesce(node.id, '')) = $query THEN 0.95
               WHEN search_text CONTAINS $query THEN 0.8
               ELSE 0.35
             END
             + 0.08 * size([token IN $query_tokens WHERE search_text CONTAINS token])
             + CASE WHEN coalesce(node.type, head(labels(node)), '') IN $target_node_types THEN 0.15 ELSE 0 END
             AS score
        {parameter_clause}
        RETURN coalesce(node.graph_id, '') AS graph_id,
               coalesce(node.id, toString(id(node))) AS node_id,
               coalesce(node.name, node.id, '') AS node_name,
               coalesce(node.type, head(labels(node)), '') AS node_type,
               coalesce(node.description, '') AS node_description,
               score AS score,
               properties(node) AS node_properties,
               {path_return}
               {parameter_return}
        ORDER BY score DESC, coalesce(node.name, node.id, '') ASC
        LIMIT toInteger($limit)
        """

    @staticmethod
    def _tenant_scoped_nodes_query() -> str:
        return """
        MATCH (node)
        WHERE node.tenant_id = $tenant_id
          AND node.graph_id = $graph_id
        OPTIONAL MATCH (node)-[out_rel]->()
        WHERE out_rel.tenant_id = $tenant_id
          AND out_rel.graph_id = $graph_id
        WITH node, count(out_rel) AS out_degree
        OPTIONAL MATCH ()-[in_rel]->(node)
        WHERE in_rel.tenant_id = $tenant_id
          AND in_rel.graph_id = $graph_id
        WITH node, out_degree, count(in_rel) AS in_degree
        WITH node, out_degree + in_degree AS degree
        ORDER BY CASE coalesce(node.type, '')
                   WHEN 'SelectionRoot' THEN 0
                   WHEN 'Catalog' THEN 1
                   WHEN 'ProductModel' THEN 2
                   WHEN 'Parameter' THEN 3
                   WHEN 'ProductField' THEN 4
                   WHEN 'ProductData' THEN 5
                   ELSE 5
                 END ASC,
                 degree DESC,
                 coalesce(node.name, node.id, '') ASC
        WITH count(node) AS node_count,
             collect({
               id: coalesce(node.id, toString(id(node))),
               name: coalesce(node.name, node.id, toString(id(node))),
               type: coalesce(node.type, head(labels(node)), ''),
               description: coalesce(node.description, ''),
               labels: coalesce(node.labels, labels(node)),
               properties: properties(node)
             })[0..toInteger($limit)] AS nodes
        RETURN node_count, nodes
        """

    @staticmethod
    def _tenant_scoped_relationships_query() -> str:
        return """
        MATCH (source)-[rel]->(target)
        WHERE source.tenant_id = $tenant_id
          AND target.tenant_id = $tenant_id
          AND source.graph_id = $graph_id
          AND target.graph_id = $graph_id
        WITH source, rel, target
        ORDER BY CASE coalesce(rel.relation_type, type(rel))
                   WHEN 'HAS_SELECTION_CATEGORY' THEN 0
                   WHEN 'HAS_CHILD_CATEGORY' THEN 1
                   WHEN 'HAS_PRODUCT_MODEL' THEN 2
                   WHEN 'DEFINES_PARAMETER' THEN 3
                   WHEN 'USES_FIELD' THEN 4
                   ELSE 5
                 END ASC,
                 coalesce(source.name, source.id, '') ASC,
                 coalesce(rel.relation_type, type(rel)) ASC,
                 coalesce(target.name, target.id, '') ASC
        WITH count(rel) AS relationship_count,
             collect({
               id: coalesce(rel.id, toString(id(rel))),
               source_id: coalesce(source.id, toString(id(source))),
               source_name: coalesce(source.name, source.id, toString(id(source))),
               relation_type: coalesce(rel.relation_type, type(rel)),
               target_id: coalesce(target.id, toString(id(target))),
               target_name: coalesce(target.name, target.id, toString(id(target))),
               confidence: coalesce(rel.confidence, 0.0),
               properties: properties(rel)
             })[0..toInteger($limit)] AS relationships
        RETURN relationship_count, relationships
        """

    @staticmethod
    def _tenant_scoped_import_nodes_query() -> str:
        return """
        UNWIND $nodes AS node
        MERGE (entity:KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id, id: node.id})
        SET entity.name = node.name,
            entity.type = node.type,
            entity.description = node.description,
            entity.labels = node.labels,
            entity += node.properties
        """

    @staticmethod
    def _tenant_scoped_import_relationships_query() -> str:
        return """
        UNWIND $relationships AS relationship
        MATCH (source:KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id, id: relationship.source_id})
        MATCH (target:KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id, id: relationship.target_id})
        MERGE (source)-[rel:KNOWLEDGE_GRAPH_RELATION {id: relationship.id}]->(target)
        SET rel.tenant_id = $tenant_id,
            rel.graph_id = $graph_id,
            rel.relation_type = relationship.relation_type,
            rel.confidence = relationship.confidence,
            rel += relationship.properties
        """

    @staticmethod
    def _tenant_scoped_delete_relationships_query() -> str:
        return """
        MATCH (:KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id})-[rel]-(
          :KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id}
        )
        WITH collect(DISTINCT rel) AS relationships
        FOREACH (rel IN relationships | DELETE rel)
        RETURN size(relationships) AS deleted_count
        """

    @staticmethod
    def _tenant_scoped_delete_nodes_query() -> str:
        return """
        MATCH (node:KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id})
        WITH collect(node) AS nodes
        FOREACH (node IN nodes | DETACH DELETE node)
        RETURN size(nodes) AS deleted_count
        """

    @staticmethod
    def _row_to_result(row: dict[str, Any]) -> GraphRetrievalResult:
        source_name = str(row.get("source_name") or "")
        relation_type = str(row.get("relation_type") or "")
        target_name = str(row.get("target_name") or "")
        content = " ".join(part for part in [source_name, relation_type, target_name] if part)
        return GraphRetrievalResult(
            graph_id=str(row.get("graph_id") or ""),
            title=source_name or target_name or "Graph path",
            content=content,
            score=float(row.get("score") or 0.0),
            metadata={
                "source_id": str(row.get("source_id") or ""),
                "source_name": source_name,
                "relation_id": str(row.get("relation_id") or ""),
                "relation_type": relation_type,
                "target_id": str(row.get("target_id") or ""),
                "target_name": target_name,
                "source": LlamaIndexNeo4jGraphRetriever._json_safe_mapping(row.get("source_properties") or {}),
                "relation": LlamaIndexNeo4jGraphRetriever._json_safe_mapping(row.get("relation_properties") or {}),
                "target": LlamaIndexNeo4jGraphRetriever._json_safe_mapping(row.get("target_properties") or {}),
            },
        )

    @staticmethod
    def _node_row_to_result(row: dict[str, Any]) -> GraphRetrievalResult:
        node_name = str(row.get("node_name") or "")
        node_type = str(row.get("node_type") or "")
        node_properties = LlamaIndexNeo4jGraphRetriever._json_safe_mapping(row.get("node_properties") or {})
        ancestor_path = LlamaIndexNeo4jGraphRetriever._json_safe_value(row.get("ancestor_path") or [])
        parameters = LlamaIndexNeo4jGraphRetriever._json_safe_value(row.get("parameters") or [])
        path_names = [
            LlamaIndexNeo4jGraphRetriever._path_display_name(item.get("name") or "")
            for item in ancestor_path
            if isinstance(item, Mapping) and item.get("name")
        ]
        path_names = LlamaIndexNeo4jGraphRetriever._collapse_path_names(path_names)
        template_display_name = LlamaIndexNeo4jGraphRetriever._template_display_name(node_name, node_properties)
        if path_names and template_display_name and path_names[-1] != template_display_name:
            full_node_path = "/".join([*path_names, template_display_name])
        elif path_names:
            full_node_path = "/".join(path_names)
        else:
            full_node_path = LlamaIndexNeo4jGraphRetriever._path_display_name(
                node_properties.get("full_node_path") or node_properties.get("path") or ""
            )
            if full_node_path and template_display_name and not full_node_path.endswith(template_display_name):
                full_node_path = "/".join([full_node_path, template_display_name])
        node_path = "/".join(path_names) if path_names else LlamaIndexNeo4jGraphRetriever._path_display_name(
            node_properties.get("path") or ""
        )
        content_parts = [node_name]
        if node_type:
            content_parts.append(f"type:{node_type}")
        if full_node_path:
            content_parts.append(f"full_node_path:{full_node_path}")
        if node_path and node_path != full_node_path:
            content_parts.append(f"node_path:{node_path}")
        if parameters:
            parameter_names = [
                str(item.get("name") or "")
                for item in parameters
                if isinstance(item, Mapping) and item.get("name")
            ]
            if parameter_names:
                content_parts.append("parameters:" + ", ".join(parameter_names))

        return GraphRetrievalResult(
            graph_id=str(row.get("graph_id") or ""),
            title=node_name or "Graph node",
            content=" ".join(content_parts),
            score=float(row.get("score") or 0.0),
            metadata={
                "node_id": str(row.get("node_id") or ""),
                "node_name": node_name,
                "node_type": node_type,
                "node_description": str(row.get("node_description") or ""),
                "full_node_path": full_node_path,
                "node_path": node_path,
                "node": node_properties,
                "ancestor_path": ancestor_path,
                "parameters": parameters,
            },
        )

    @staticmethod
    def _row_to_overview_node(row: dict[str, Any]) -> GraphOverviewNode:
        return GraphOverviewNode(
            id=str(row.get("id") or ""),
            name=str(row.get("name") or ""),
            type=str(row.get("type") or ""),
            description=str(row.get("description") or ""),
            labels=[str(label) for label in row.get("labels", []) if label],
            properties=LlamaIndexNeo4jGraphRetriever._json_safe_mapping(row.get("properties") or {}),
        )

    @staticmethod
    def _row_to_overview_relationship(row: dict[str, Any]) -> GraphOverviewRelationship:
        return GraphOverviewRelationship(
            id=str(row.get("id") or ""),
            source_id=str(row.get("source_id") or ""),
            source_name=str(row.get("source_name") or ""),
            relation_type=str(row.get("relation_type") or ""),
            target_id=str(row.get("target_id") or ""),
            target_name=str(row.get("target_name") or ""),
            confidence=float(row.get("confidence") or 0.0),
            properties=LlamaIndexNeo4jGraphRetriever._json_safe_mapping(row.get("properties") or {}),
        )

    @staticmethod
    def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key): LlamaIndexNeo4jGraphRetriever._json_safe_value(item) for key, item in value.items()}

    @staticmethod
    def _json_safe_value(value: Any) -> Any:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime | date):
            return value.isoformat()
        if hasattr(value, "iso_format"):
            return value.iso_format()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, Mapping):
            return LlamaIndexNeo4jGraphRetriever._json_safe_mapping(value)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            return [LlamaIndexNeo4jGraphRetriever._json_safe_value(item) for item in value]
        return str(value)

    @staticmethod
    def _path_display_name(value: Any) -> str:
        return str(value or "").strip().strip("/")

    @staticmethod
    def _collapse_path_names(path_names: list[str]) -> list[str]:
        normalized = [path_name for path_name in path_names if path_name]
        collapsed: list[str] = []
        for path_name in normalized:
            if collapsed and path_name.startswith(collapsed[-1] + "/"):
                collapsed[-1] = path_name
                continue
            collapsed.append(path_name)
        return collapsed

    @staticmethod
    def _template_display_name(node_name: str, node_properties: Mapping[str, Any]) -> str:
        template_name = str(
            node_properties.get("template_name")
            or node_properties.get("template")
            or node_properties.get("file_name")
            or ""
        ).strip()
        if template_name:
            return template_name
        return node_name.strip()

    @staticmethod
    def _query_tokens(query: str) -> list[str]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        tokens: list[str] = []
        current = ""
        cjk_current = ""

        def flush_current() -> None:
            nonlocal current, cjk_current
            if current:
                tokens.append(current)
                current = ""
            if cjk_current:
                tokens.extend(LlamaIndexNeo4jGraphRetriever._cjk_ngrams(cjk_current))
                cjk_current = ""

        for char in normalized:
            if char.isalnum() or "\u4e00" <= char <= "\u9fff":
                current += char
                if "\u4e00" <= char <= "\u9fff":
                    cjk_current += char
                else:
                    if cjk_current:
                        tokens.extend(LlamaIndexNeo4jGraphRetriever._cjk_ngrams(cjk_current))
                        cjk_current = ""
                continue
            flush_current()
        flush_current()
        if normalized not in tokens:
            tokens.insert(0, normalized)
        return [token for token in dict.fromkeys(tokens) if token]

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        terms = []
        current = ""
        for char in normalized:
            if char.isalnum() or "\u4e00" <= char <= "\u9fff":
                current += char
                continue
            if current:
                terms.append(current)
                current = ""
        if current:
            terms.append(current)
        return [term for term in dict.fromkeys(terms) if term]

    @staticmethod
    def _cjk_ngrams(value: str) -> list[str]:
        if len(value) <= 2:
            return [value]
        tokens = [value]
        max_size = min(len(value), 6)
        for size in range(2, max_size + 1):
            tokens.extend(value[index : index + size] for index in range(0, len(value) - size + 1))
        return tokens

    @staticmethod
    def _deduplicate_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        seen = set()
        deduplicated_rows = []
        for row in rows:
            row_key = row.get(key)
            if row_key in seen:
                continue
            seen.add(row_key)
            deduplicated_rows.append(row)
        return deduplicated_rows
