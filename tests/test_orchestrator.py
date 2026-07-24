import uuid
from unittest.mock import MagicMock, patch

from research_mapper import taxonomy
from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.models.taxonomy_search import (
    Concept,
    ConceptFilterGroup,
    IndexedVocab,
)
from research_mapper.orchestrator import ResearchMappingOrchestrator


def test_retrieve_evidence_deduplicates_evidence():
    """Evidence returned from multiple search queries is deduplicated."""
    agent = ResearchMappingOrchestrator()

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


def test_generate_concept_filters_resolves_local_refs_to_iris():
    """_generate_concept_filters resolves the LLM's chosen local_refs back to IRIs."""
    agent = ResearchMappingOrchestrator()

    indexed = IndexedVocab(
        concepts=[Concept(local_ref="C0", scheme="Country", label="Kenya")],
        local_ref_to_iri={"C0": "https://vocab.example.org/Country/KE"},
    )

    mock_prediction = MagicMock()
    mock_prediction.filter_groups = [
        ConceptFilterGroup(
            scheme="Country", concept_local_refs=["C0"], reason="Kenya-specific query"
        )
    ]
    agent.concept_filter_generator = MagicMock(return_value=mock_prediction)

    with (
        patch("research_mapper.taxonomy.get_taxonomy", return_value={}),
        patch("research_mapper.taxonomy.build_concept_index", return_value=indexed),
    ):
        result = agent._generate_concept_filters(UserQuery(query="HPV in Kenya"))

    assert result == [["https://vocab.example.org/Country/KE"]]


def test_gather_evidence_by_concepts_retrieves_via_resolved_filters():
    """_gather_evidence_by_concepts retrieves evidence using the generated concept filters."""
    agent = ResearchMappingOrchestrator()
    expected_evidence = [Evidence(destiny_id=uuid.uuid4())]

    agent._generate_concept_filters = MagicMock(
        return_value=[["https://vocab.example.org/Country/KE"]]
    )

    with patch(
        "research_mapper.orchestrator.retrieve_evidence_by_concepts",
        return_value=expected_evidence,
    ) as mock_retrieve:
        result = agent._gather_evidence_by_concepts(UserQuery(query="test"))

    mock_retrieve.assert_called_once_with(
        taxonomy.RepoCommunity.HPV, [["https://vocab.example.org/Country/KE"]]
    )
    assert result == expected_evidence
