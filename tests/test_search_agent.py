"""
Original end-to-end test, now marked as an integration test.
See test_integration.py for expanded live test coverage.
"""

import pytest

from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.modules.sparse_search import EvidenceRetriever
from research_mapper.taxonomy import RepoCommunity


@pytest.mark.integration
def test_evidence_retriever_end_to_end():
    retriever = EvidenceRetriever()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )
    search_query = LuceneQuery(query="climate AND health")

    result = retriever(
        user_query=query, search_query=search_query, community=RepoCommunity.HPV
    )

    assert result.evidence, "Expected at least one evidence item"
    for item in result.evidence:
        assert isinstance(item, Evidence)
