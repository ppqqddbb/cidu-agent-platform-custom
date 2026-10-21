from unittest.mock import MagicMock, patch
from uuid import uuid4

from controllers.service_api.knowledge_graph import KnowledgeGraphSyncApi


def test_knowledge_graph_sync_api_uses_tenant_from_dataset_token(app):
    tenant_id = str(uuid4())
    graph_id = uuid4()
    payload = {
        "nodes": [
            {"id": "database:1", "name": "jiavusystemdata", "type": "Database"},
            {"id": "table:1", "name": "product_model", "type": "Table"},
        ],
        "edges": [
            {"source": "database:1", "target": "table:1", "type": "HAS_TABLE"},
        ],
    }
    sync_result = MagicMock()
    sync_result.model_dump.return_value = {
        "node_count": 2,
        "relationship_count": 1,
        "deleted_node_count": 10,
        "deleted_relationship_count": 9,
    }

    with app.test_request_context(f"/knowledge-graphs/{graph_id}/sync", method="POST", json=payload):
        with patch("controllers.service_api.knowledge_graph.KnowledgeGraphService") as service_cls:
            service_cls.return_value.sync_template.return_value = sync_result

            response, status_code = KnowledgeGraphSyncApi().post(tenant_id, graph_id)

    assert status_code == 200
    assert response == {
        "node_count": 2,
        "relationship_count": 1,
        "deleted_node_count": 10,
        "deleted_relationship_count": 9,
    }
    service_cls.return_value.sync_template.assert_called_once()
    kwargs = service_cls.return_value.sync_template.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["graph_id"] == str(graph_id)
    assert kwargs["template"].relationships[0].relation_type == "HAS_TABLE"
