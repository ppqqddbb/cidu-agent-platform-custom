"""Application service for standalone knowledge graph operations."""

from sqlalchemy import func, select

from core.knowledge_graph.entities import (
    GraphImportResult,
    GraphImportTemplate,
    GraphOverview,
    GraphRetrievalRequest,
    GraphRetrievalResult,
    GraphSyncResult,
    GraphSyncTemplate,
)
from core.knowledge_graph.llama_index_neo4j_retriever import LlamaIndexNeo4jGraphRetriever
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.knowledge_graph import KnowledgeGraph


class KnowledgeGraphService:
    """
    Coordinates standalone knowledge graph resources without depending on Dify dataset models.

    Graph libraries are relational metadata rows. Neo4j stores their extracted content using the row ID as `graph_id`,
    which keeps list/create/delete independent from graph indexing and future hybrid retrieval.
    """

    def __init__(self, retriever: LlamaIndexNeo4jGraphRetriever | None = None) -> None:
        self._retriever = retriever or LlamaIndexNeo4jGraphRetriever()

    @staticmethod
    def list_graphs(
        tenant_id: str,
        page: int,
        limit: int,
        keyword: str | None = None,
    ) -> tuple[list[KnowledgeGraph], int]:
        stmt = select(KnowledgeGraph).where(
            KnowledgeGraph.tenant_id == tenant_id,
            KnowledgeGraph.archived.is_(False),
        )
        count_stmt = select(func.count(KnowledgeGraph.id)).where(
            KnowledgeGraph.tenant_id == tenant_id,
            KnowledgeGraph.archived.is_(False),
        )
        if keyword:
            escaped_keyword = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like_keyword = f"%{escaped_keyword}%"
            stmt = stmt.where(KnowledgeGraph.name.ilike(like_keyword, escape="\\"))
            count_stmt = count_stmt.where(KnowledgeGraph.name.ilike(like_keyword, escape="\\"))

        graphs = db.session.scalars(
            stmt.order_by(KnowledgeGraph.created_at.desc()).offset((page - 1) * limit).limit(limit)
        ).all()
        total = db.session.scalar(count_stmt) or 0
        return list(graphs), total

    @staticmethod
    def create_graph(tenant_id: str, user_id: str, name: str, description: str = "") -> KnowledgeGraph:
        if db.session.scalar(
            select(KnowledgeGraph.id).where(
                KnowledgeGraph.tenant_id == tenant_id,
                KnowledgeGraph.name == name,
                KnowledgeGraph.archived.is_(False),
            )
        ):
            raise ValueError("knowledge graph name already exists")

        graph = KnowledgeGraph(
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_by=user_id,
            updated_by=user_id,
        )
        db.session.add(graph)
        db.session.commit()
        return graph

    @staticmethod
    def get_graph(tenant_id: str, graph_id: str) -> KnowledgeGraph:
        graph = db.session.scalar(
            select(KnowledgeGraph).where(
                KnowledgeGraph.id == graph_id,
                KnowledgeGraph.tenant_id == tenant_id,
                KnowledgeGraph.archived.is_(False),
            )
        )
        if graph is None:
            raise ValueError("knowledge graph not found")
        return graph

    @staticmethod
    def delete_graph(tenant_id: str, graph_id: str, user_id: str) -> None:
        graph = db.session.scalar(
            select(KnowledgeGraph).where(
                KnowledgeGraph.id == graph_id,
                KnowledgeGraph.tenant_id == tenant_id,
                KnowledgeGraph.archived.is_(False),
            )
        )
        if graph is None:
            raise ValueError("knowledge graph not found")

        # Archive first. Neo4j content cleanup should be an explicit async task because graph deletion can be large.
        graph.archived = True
        graph.archived_at = naive_utc_now()
        graph.updated_by = user_id
        db.session.commit()

    def retrieve(self, request: GraphRetrievalRequest) -> list[GraphRetrievalResult]:
        return self._retriever.retrieve(request)

    def search_graph(self, tenant_id: str, graph_id: str, query: str, top_k: int) -> list[GraphRetrievalResult]:
        self.get_graph(tenant_id, graph_id)
        return self.retrieve(
            GraphRetrievalRequest(
                tenant_id=tenant_id,
                graph_ids=[graph_id],
                query=query,
                top_k=top_k,
            )
        )

    def get_overview(self, tenant_id: str, graph_id: str, limit: int = 50) -> GraphOverview:
        self.get_graph(tenant_id, graph_id)
        return self._retriever.get_overview(tenant_id=tenant_id, graph_id=graph_id, limit=limit)

    def import_template(
        self,
        tenant_id: str,
        graph_id: str,
        template: GraphImportTemplate,
        user_id: str | None = None,
    ) -> GraphImportResult:
        graph = self.get_graph(tenant_id, graph_id)
        result = self._retriever.import_template(tenant_id=tenant_id, graph_id=graph_id, template=template)
        if user_id:
            graph.updated_by = user_id
            db.session.commit()
        return result

    def sync_template(
        self,
        tenant_id: str,
        graph_id: str,
        template: GraphSyncTemplate,
        user_id: str | None = None,
    ) -> GraphSyncResult:
        """Replace or upsert a full tenant-scoped graph template from service API automation."""
        graph = self.get_graph(tenant_id, graph_id)
        result = self._retriever.sync_template(tenant_id=tenant_id, graph_id=graph_id, template=template)
        if user_id:
            graph.updated_by = user_id
            db.session.commit()
        return result
