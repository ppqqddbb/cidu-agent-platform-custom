import pytest
from pydantic import ValidationError

from controllers.console.knowledge_graph import KnowledgeGraphOverviewQuery


def test_knowledge_graph_overview_query_allows_two_thousand_nodes():
    query = KnowledgeGraphOverviewQuery.model_validate({"limit": "2000"})

    assert query.limit == 2000


def test_knowledge_graph_overview_query_rejects_limits_above_two_thousand():
    with pytest.raises(ValidationError):
        KnowledgeGraphOverviewQuery.model_validate({"limit": "2001"})
