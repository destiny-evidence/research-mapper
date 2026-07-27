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
from research_mapper.orchestrator import ResearchMappingOrchestrator, SearchMode


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

    filter_group = ConceptFilterGroup(
        scheme="Country", concept_local_refs=["C0"], reason="Kenya-specific query"
    )
    mock_prediction = MagicMock()
    mock_prediction.filter_groups = [filter_group]
    agent.concept_filter_generator = MagicMock(return_value=mock_prediction)

    with (
        patch("research_mapper.taxonomy.get_taxonomy", return_value={}),
        patch("research_mapper.taxonomy.build_concept_index", return_value=indexed),
    ):
        filter_groups, concepts = agent._generate_concept_filters(
            UserQuery(query="HPV in Kenya"), taxonomy.RepoCommunity.HPV
        )

    assert filter_groups == [filter_group]
    assert concepts == [["https://vocab.example.org/Country/KE"]]


def test_generate_concept_filters_does_not_wrap_generator_in_live_streaming():
    """
    Regression test: the concept-filter agent can call interactive UI tools mid-run
    (ask_for_clarification), which breaks under run_with_status's rich.Live wrapper —
    the generator must be called directly, with reasoning printed only after it returns.
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)

    indexed = IndexedVocab(
        concepts=[Concept(local_ref="C0", scheme="Country", label="Kenya")],
        local_ref_to_iri={"C0": "https://vocab.example.org/Country/KE"},
    )
    mock_prediction = MagicMock()
    mock_prediction.filter_groups = []
    mock_prediction.reasoning = "some reasoning"
    agent.concept_filter_generator = MagicMock(return_value=mock_prediction)

    with (
        patch("research_mapper.taxonomy.get_taxonomy", return_value={}),
        patch("research_mapper.taxonomy.build_concept_index", return_value=indexed),
    ):
        agent._generate_concept_filters(
            UserQuery(query="test"), taxonomy.RepoCommunity.HPV
        )

    agent.concept_filter_generator.assert_called_once_with(
        user_query=UserQuery(query="test"), taxonomy_concepts=indexed.concepts
    )
    mock_tui.run_with_status.assert_not_called()
    mock_tui.print_reasoning.assert_called_once_with(
        "Concept filters", "some reasoning"
    )


def test_gather_evidence_by_concepts_retrieves_via_resolved_filters():
    """_gather_evidence_by_concepts dispatches the retrieval subagent with resolved filters."""
    agent = ResearchMappingOrchestrator()
    expected_evidence = [Evidence(destiny_id=uuid.uuid4())]
    filter_group = ConceptFilterGroup(
        scheme="Country", concept_local_refs=["C0"], reason="Kenya-specific query"
    )

    agent._generate_concept_filters = MagicMock(
        return_value=([filter_group], [["https://vocab.example.org/Country/KE"]])
    )
    mock_prediction = MagicMock()
    mock_prediction.evidence = expected_evidence
    agent.concept_evidence_retriever = MagicMock(return_value=mock_prediction)

    result = agent._gather_evidence_by_concepts(
        UserQuery(query="test"), taxonomy.RepoCommunity.HPV
    )

    agent.concept_evidence_retriever.assert_called_once_with(
        user_query=UserQuery(query="test"),
        community=taxonomy.RepoCommunity.HPV,
        filter_groups=[filter_group],
        concepts=[["https://vocab.example.org/Country/KE"]],
    )
    assert result == expected_evidence


def test_gather_evidence_by_concepts_does_not_wrap_retriever_in_live_streaming():
    """
    Regression test: ConceptEvidenceRetriever builds its ReAct fresh inside forward(),
    with no persistent named-predictor attribute for dspy.streamify to find — wrapping it
    in run_with_status raises TypeError. Must call the retriever directly, with reasoning
    printed only after it returns (same reasoning EvidenceRetriever is only ever called
    via .batch(), never run_with_status).
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    filter_group = ConceptFilterGroup(
        scheme="Country", concept_local_refs=["C0"], reason="Kenya-specific query"
    )

    agent._generate_concept_filters = MagicMock(
        return_value=([filter_group], [["https://vocab.example.org/Country/KE"]])
    )
    mock_prediction = MagicMock()
    mock_prediction.evidence = []
    mock_prediction.reasoning = "some reasoning"
    agent.concept_evidence_retriever = MagicMock(return_value=mock_prediction)

    agent._gather_evidence_by_concepts(
        UserQuery(query="test"), taxonomy.RepoCommunity.HPV
    )

    agent.concept_evidence_retriever.assert_called_once_with(
        user_query=UserQuery(query="test"),
        community=taxonomy.RepoCommunity.HPV,
        filter_groups=[filter_group],
        concepts=[["https://vocab.example.org/Country/KE"]],
    )
    mock_tui.run_with_status.assert_not_called()
    mock_tui.print_reasoning.assert_called_once_with(
        "Concept evidence", "some reasoning"
    )


def test_run_dispatches_to_sparse_search_by_default():
    """run() defaults to sparse search."""
    agent = ResearchMappingOrchestrator()
    agent._gather_evidence = MagicMock(return_value=[])
    agent._gather_evidence_by_concepts = MagicMock(return_value=[])
    agent._screen_evidence = MagicMock(return_value=[])
    agent._map_evidence = MagicMock()

    agent.run(UserQuery(query="test"))

    agent._gather_evidence.assert_called_once_with(UserQuery(query="test"))
    agent._gather_evidence_by_concepts.assert_not_called()


def test_run_dispatches_to_taxonomy_search_with_chosen_community():
    """run() gathers evidence via concept filters when search_mode is TAXONOMY."""
    agent = ResearchMappingOrchestrator()
    agent._gather_evidence = MagicMock(return_value=[])
    agent._gather_evidence_by_concepts = MagicMock(return_value=[])
    agent._screen_evidence = MagicMock(return_value=[])
    agent._map_evidence = MagicMock()

    agent.run(
        UserQuery(query="test"),
        search_mode=SearchMode.TAXONOMY,
        community=taxonomy.RepoCommunity.ESEA,
    )

    agent._gather_evidence_by_concepts.assert_called_once_with(
        UserQuery(query="test"), taxonomy.RepoCommunity.ESEA
    )
    agent._gather_evidence.assert_not_called()
