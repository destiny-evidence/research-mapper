import uuid
from unittest.mock import MagicMock

from research_mapper.models import Evidence, LuceneQuery, UserQuery
from research_mapper.modules.workflow_agent import WorkflowAgent


def test_retrieve_evidence_deduplicates_evidence():
    """Evidence returned from multiple search queries is deduplicated."""
    agent = WorkflowAgent()

    shared_id = uuid.uuid4()
    shared_evidence = Evidence(destiny_id=shared_id)

    search_queries = [LuceneQuery(query="q1"), LuceneQuery(query="q2")]

    mock_prediction = MagicMock()
    mock_prediction.evidence = [shared_evidence]
    mock_prediction.reasoning = "reasoning"
    agent.evidence_retriever.batch = MagicMock(
        return_value=[mock_prediction, mock_prediction]
    )

    result = agent._retrieve_evidence(UserQuery(query="test"), search_queries)

    assert len(result) == 1
