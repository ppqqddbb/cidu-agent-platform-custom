from typing import Any

from flask import request
from flask_restx import Resource, fields, marshal
from pydantic import BaseModel, Field, PositiveInt, ValidationError

from controllers.common.schema import get_or_create_model, register_schema_models
from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    capability_any_required,
    setup_required,
)
from core.knowledge_graph.entities import GraphImportNode, GraphImportRelationship, GraphImportTemplate
from graphon.model_runtime.utils.encoders import jsonable_encoder
from libs.login import current_account_with_tenant, login_required
from models.knowledge_graph import KnowledgeGraph
from services.knowledge_graph_service import KnowledgeGraphService

knowledge_graph_fields = {
    "id": fields.String,
    "tenant_id": fields.String,
    "name": fields.String,
    "description": fields.String,
    "created_by": fields.String,
    "updated_by": fields.String,
    "created_at": fields.DateTime(dt_format="iso8601"),
    "updated_at": fields.DateTime(dt_format="iso8601"),
}

knowledge_graph_model = get_or_create_model("KnowledgeGraph", knowledge_graph_fields)
knowledge_graph_list_model = get_or_create_model(
    "KnowledgeGraphList",
    {
        "data": fields.List(fields.Nested(knowledge_graph_model)),
        "has_more": fields.Boolean,
        "limit": fields.Integer,
        "total": fields.Integer,
        "page": fields.Integer,
    },
)
knowledge_graph_search_result_model = get_or_create_model(
    "KnowledgeGraphSearchResult",
    {
        "graph_id": fields.String,
        "title": fields.String,
        "content": fields.String,
        "score": fields.Float,
        "metadata": fields.Raw,
    },
)
knowledge_graph_search_result_list_model = get_or_create_model(
    "KnowledgeGraphSearchResultList",
    {
        "data": fields.List(fields.Nested(knowledge_graph_search_result_model)),
    },
)
knowledge_graph_overview_node_model = get_or_create_model(
    "KnowledgeGraphOverviewNode",
    {
        "id": fields.String,
        "name": fields.String,
        "type": fields.String,
        "description": fields.String,
        "labels": fields.List(fields.String),
        "properties": fields.Raw,
    },
)
knowledge_graph_overview_relationship_model = get_or_create_model(
    "KnowledgeGraphOverviewRelationship",
    {
        "id": fields.String,
        "source_id": fields.String,
        "source_name": fields.String,
        "relation_type": fields.String,
        "target_id": fields.String,
        "target_name": fields.String,
        "confidence": fields.Float,
        "properties": fields.Raw,
    },
)
knowledge_graph_overview_model = get_or_create_model(
    "KnowledgeGraphOverview",
    {
        "node_count": fields.Integer,
        "relationship_count": fields.Integer,
        "nodes": fields.List(fields.Nested(knowledge_graph_overview_node_model)),
        "relationships": fields.List(fields.Nested(knowledge_graph_overview_relationship_model)),
    },
)
knowledge_graph_import_result_model = get_or_create_model(
    "KnowledgeGraphImportResult",
    {
        "node_count": fields.Integer,
        "relationship_count": fields.Integer,
    },
)


class KnowledgeGraphListQuery(BaseModel):
    page: PositiveInt = Field(default=1)
    limit: PositiveInt = Field(default=30, le=100)
    keyword: str | None = Field(default=None, max_length=80)


class KnowledgeGraphCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)


class KnowledgeGraphSearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    top_k: PositiveInt = Field(default=10, le=50)


class KnowledgeGraphOverviewQuery(BaseModel):
    limit: PositiveInt = Field(default=100, le=2000)


register_schema_models(
    console_ns,
    KnowledgeGraphListQuery,
    KnowledgeGraphCreatePayload,
    KnowledgeGraphSearchQuery,
    KnowledgeGraphOverviewQuery,
    GraphImportNode,
    GraphImportRelationship,
    GraphImportTemplate,
)


def _graph_to_dict(graph: KnowledgeGraph) -> dict[str, Any]:
    return marshal(graph, knowledge_graph_fields)


@console_ns.route("/knowledge-graphs")
class KnowledgeGraphListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.list", "dataset.read")
    @console_ns.response(200, "Knowledge graphs retrieved successfully", knowledge_graph_list_model)
    def get(self):
        _, tenant_id = current_account_with_tenant()
        query = KnowledgeGraphListQuery.model_validate(request.args.to_dict())
        graphs, total = KnowledgeGraphService.list_graphs(
            tenant_id=tenant_id,
            page=query.page,
            limit=query.limit,
            keyword=query.keyword,
        )
        return {
            "data": [_graph_to_dict(graph) for graph in graphs],
            "has_more": len(graphs) == query.limit,
            "limit": query.limit,
            "total": total,
            "page": query.page,
        }, 200

    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.create", "dataset.update")
    @console_ns.expect(console_ns.models[KnowledgeGraphCreatePayload.__name__])
    @console_ns.response(201, "Knowledge graph created successfully", knowledge_graph_model)
    def post(self):
        account, tenant_id = current_account_with_tenant()
        payload = KnowledgeGraphCreatePayload.model_validate(console_ns.payload or {})
        graph = KnowledgeGraphService.create_graph(
            tenant_id=tenant_id,
            user_id=account.id,
            name=payload.name,
            description=payload.description,
        )
        return _graph_to_dict(graph), 201


@console_ns.route("/knowledge-graphs/<uuid:graph_id>")
class KnowledgeGraphApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.list", "dataset.read")
    @console_ns.response(200, "Knowledge graph retrieved successfully", knowledge_graph_model)
    def get(self, graph_id):
        _, tenant_id = current_account_with_tenant()
        graph = KnowledgeGraphService.get_graph(tenant_id=tenant_id, graph_id=str(graph_id))
        return _graph_to_dict(graph), 200

    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.delete", "dataset.update")
    @console_ns.response(204, "Knowledge graph deleted successfully")
    def delete(self, graph_id):
        account, tenant_id = current_account_with_tenant()
        KnowledgeGraphService.delete_graph(tenant_id=tenant_id, graph_id=str(graph_id), user_id=account.id)
        return "", 204


@console_ns.route("/knowledge-graphs/<uuid:graph_id>/search")
class KnowledgeGraphSearchApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.list", "dataset.read")
    @console_ns.response(200, "Knowledge graph search completed successfully", knowledge_graph_search_result_list_model)
    def get(self, graph_id):
        _, tenant_id = current_account_with_tenant()
        query = KnowledgeGraphSearchQuery.model_validate(request.args.to_dict())
        results = KnowledgeGraphService().search_graph(
            tenant_id=tenant_id,
            graph_id=str(graph_id),
            query=query.query,
            top_k=query.top_k,
        )
        return {
            "data": [jsonable_encoder(result.model_dump()) for result in results],
        }, 200


@console_ns.route("/knowledge-graphs/<uuid:graph_id>/overview")
class KnowledgeGraphOverviewApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.list", "dataset.read")
    @console_ns.response(200, "Knowledge graph overview retrieved successfully", knowledge_graph_overview_model)
    def get(self, graph_id):
        _, tenant_id = current_account_with_tenant()
        query = KnowledgeGraphOverviewQuery.model_validate(request.args.to_dict())
        overview = KnowledgeGraphService().get_overview(
            tenant_id=tenant_id,
            graph_id=str(graph_id),
            limit=query.limit,
        )
        return jsonable_encoder(overview.model_dump()), 200


@console_ns.route("/knowledge-graphs/<uuid:graph_id>/import")
class KnowledgeGraphImportApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @capability_any_required("dataset.create", "dataset.update")
    @console_ns.expect(console_ns.models[GraphImportTemplate.__name__])
    @console_ns.response(200, "Knowledge graph template imported successfully", knowledge_graph_import_result_model)
    def post(self, graph_id):
        account, tenant_id = current_account_with_tenant()
        try:
            template = GraphImportTemplate.model_validate(console_ns.payload or {})
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        result = KnowledgeGraphService().import_template(
            tenant_id=tenant_id,
            graph_id=str(graph_id),
            template=template,
            user_id=account.id,
        )
        return jsonable_encoder(result.model_dump()), 200
