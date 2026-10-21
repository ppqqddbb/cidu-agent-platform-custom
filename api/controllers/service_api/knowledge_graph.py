"""Service API endpoints for standalone knowledge graph automation."""

from typing import Any

from flask_restx import Resource, fields
from pydantic import ValidationError

from controllers.common.schema import get_or_create_model, register_schema_models
from controllers.service_api import service_api_ns
from controllers.service_api.wraps import validate_dataset_token
from core.knowledge_graph.entities import GraphSyncTemplate
from graphon.model_runtime.utils.encoders import jsonable_encoder
from libs.login import current_user
from services.knowledge_graph_service import KnowledgeGraphService

knowledge_graph_sync_result_model = get_or_create_model(
    "KnowledgeGraphSyncResult",
    {
        "node_count": fields.Integer,
        "relationship_count": fields.Integer,
        "deleted_node_count": fields.Integer,
        "deleted_relationship_count": fields.Integer,
    },
)

register_schema_models(service_api_ns, GraphSyncTemplate)


@service_api_ns.route("/knowledge-graphs/<uuid:graph_id>/sync")
class KnowledgeGraphSyncApi(Resource):
    """
    Import a complete standalone graph through dataset API key authentication.

    Console graph import is intentionally small and cookie-authenticated. Production sync jobs need the same tenant
    boundary as dataset APIs, plus a replace mode so removed JiaYu rows do not linger in Neo4j.
    """

    method_decorators = [validate_dataset_token]

    @service_api_ns.expect(service_api_ns.models[GraphSyncTemplate.__name__])
    @service_api_ns.doc("sync_knowledge_graph")
    @service_api_ns.doc(description="Replace or upsert a complete standalone knowledge graph")
    @service_api_ns.doc(params={"graph_id": "Knowledge graph ID"})
    @service_api_ns.doc(
        responses={
            200: "Knowledge graph synced successfully",
            401: "Unauthorized - invalid API token",
            400: "Bad request - invalid graph template",
        }
    )
    @service_api_ns.response(200, "Knowledge graph synced successfully", knowledge_graph_sync_result_model)
    def post(self, tenant_id: str, graph_id: Any):
        """Replace or upsert a complete graph for the API token's tenant."""
        try:
            template = GraphSyncTemplate.model_validate(service_api_ns.payload or {})
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        result = KnowledgeGraphService().sync_template(
            tenant_id=str(tenant_id),
            graph_id=str(graph_id),
            template=template,
            user_id=getattr(current_user, "id", None),
        )
        return jsonable_encoder(result.model_dump()), 200
