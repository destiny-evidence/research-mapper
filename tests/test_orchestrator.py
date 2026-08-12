import uuid
from unittest.mock import MagicMock, patch

import pytest

from research_mapper import taxonomy
from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.mapping import (
    EvidenceMap,
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.models.screening import ScreeningCriterion, ScreeningCriterionType
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.models.taxonomy_search import (
    Concept,
    ConceptFilterGroup,
    IndexedVocab,
)
from research_mapper.orchestrator import (
    NoEvidenceToActOnError,
    ResearchMappingOrchestrator,
    SearchMode,
    UnsatisfiableQueryError,
)


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
    mock_prediction.unsatisfiable_reason = None
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
    mock_prediction.unsatisfiable_reason = None
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


def test_generate_concept_filters_raises_when_agent_flags_unsatisfiable():
    """_generate_concept_filters raises UnsatisfiableQueryError when the agent flags
    the query as unsatisfiable, and does not attempt to resolve any filter_groups."""
    agent = ResearchMappingOrchestrator()

    indexed = IndexedVocab(
        concepts=[Concept(local_ref="C0", scheme="Country", label="Kenya")],
        local_ref_to_iri={"C0": "https://vocab.example.org/Country/KE"},
    )
    mock_prediction = MagicMock()
    mock_prediction.filter_groups = []
    mock_prediction.reasoning = "no matching concepts exist"
    mock_prediction.unsatisfiable_reason = "No concept covers this topic."
    agent.concept_filter_generator = MagicMock(return_value=mock_prediction)

    with (
        patch("research_mapper.taxonomy.get_taxonomy", return_value={}),
        patch("research_mapper.taxonomy.build_concept_index", return_value=indexed),
        pytest.raises(UnsatisfiableQueryError, match="No concept covers this topic."),
    ):
        agent._generate_concept_filters(
            UserQuery(query="test"), taxonomy.RepoCommunity.HPV
        )


def test_generate_concept_filters_displays_resolved_labels():
    """Displays the generated filter groups with concept local_refs resolved to labels,
    not raw local_refs (which are meaningless to the user)."""
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)

    indexed = IndexedVocab(
        concepts=[
            Concept(local_ref="C0", scheme="Country", label="Kenya"),
            Concept(local_ref="C1", scheme="Country", label="Uganda"),
        ],
        local_ref_to_iri={
            "C0": "https://vocab.example.org/Country/KE",
            "C1": "https://vocab.example.org/Country/UG",
        },
    )
    filter_group = ConceptFilterGroup(
        scheme="Country", concept_local_refs=["C0", "C1"], reason="East Africa focus"
    )
    mock_prediction = MagicMock()
    mock_prediction.filter_groups = [filter_group]
    mock_prediction.reasoning = "some reasoning"
    mock_prediction.unsatisfiable_reason = None
    agent.concept_filter_generator = MagicMock(return_value=mock_prediction)

    with (
        patch("research_mapper.taxonomy.get_taxonomy", return_value={}),
        patch("research_mapper.taxonomy.build_concept_index", return_value=indexed),
    ):
        agent._generate_concept_filters(
            UserQuery(query="test"), taxonomy.RepoCommunity.HPV
        )

    mock_tui.print_table.assert_called_once()
    args, kwargs = mock_tui.print_table.call_args
    assert args[0] == [filter_group]
    assert kwargs["title"] == "Concept filters to apply"
    assert kwargs["label"](filter_group) == (
        "[bold]Country[/bold]: Kenya, Uganda\n[dim]East Africa focus[/dim]"
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


def test_gather_all_evidence_defaults_to_sparse_only():
    """_gather_all_evidence defaults to sparse-only when search_modes is None."""
    agent = ResearchMappingOrchestrator()
    agent._gather_evidence_by_queries = MagicMock(return_value=[])
    agent._gather_evidence_by_concepts = MagicMock(return_value=[])

    agent._gather_all_evidence(
        UserQuery(query="test"), None, taxonomy.RepoCommunity.HPV
    )

    agent._gather_evidence_by_queries.assert_called_once_with(UserQuery(query="test"))
    agent._gather_evidence_by_concepts.assert_not_called()


def test_gather_all_evidence_sparse_only():
    agent = ResearchMappingOrchestrator()
    agent._gather_evidence_by_queries = MagicMock(return_value=[])
    agent._gather_evidence_by_concepts = MagicMock(return_value=[])

    agent._gather_all_evidence(
        UserQuery(query="test"), {SearchMode.SPARSE}, taxonomy.RepoCommunity.HPV
    )

    agent._gather_evidence_by_queries.assert_called_once_with(UserQuery(query="test"))
    agent._gather_evidence_by_concepts.assert_not_called()


def test_gather_all_evidence_taxonomy_only_with_chosen_community():
    agent = ResearchMappingOrchestrator()
    agent._gather_evidence_by_queries = MagicMock(return_value=[])
    agent._gather_evidence_by_concepts = MagicMock(return_value=[])

    agent._gather_all_evidence(
        UserQuery(query="test"), {SearchMode.TAXONOMY}, taxonomy.RepoCommunity.ESEA
    )

    agent._gather_evidence_by_concepts.assert_called_once_with(
        UserQuery(query="test"), taxonomy.RepoCommunity.ESEA
    )
    agent._gather_evidence_by_queries.assert_not_called()


def test_gather_all_evidence_both_modes_runs_taxonomy_before_sparse():
    """When both modes are selected, taxonomy search runs first, then sparse search."""
    agent = ResearchMappingOrchestrator()
    call_order = []
    agent._gather_evidence_by_concepts = MagicMock(
        side_effect=lambda *a: call_order.append("taxonomy") or []
    )
    agent._gather_evidence_by_queries = MagicMock(
        side_effect=lambda *a: call_order.append("sparse") or []
    )

    agent._gather_all_evidence(
        UserQuery(query="test"),
        {SearchMode.SPARSE, SearchMode.TAXONOMY},
        taxonomy.RepoCommunity.HPV,
    )

    assert call_order == ["taxonomy", "sparse"]


def test_gather_all_evidence_both_modes_deduplicates_overlapping_evidence():
    """Evidence returned by both modes (same destiny_id) is deduplicated in the union."""
    agent = ResearchMappingOrchestrator()
    shared_id = uuid.uuid4()
    shared_evidence = Evidence(destiny_id=shared_id)
    only_sparse = Evidence(destiny_id=uuid.uuid4())

    agent._gather_evidence_by_concepts = MagicMock(return_value=[shared_evidence])
    agent._gather_evidence_by_queries = MagicMock(
        return_value=[shared_evidence, only_sparse]
    )

    result = agent._gather_all_evidence(
        UserQuery(query="test"),
        {SearchMode.SPARSE, SearchMode.TAXONOMY},
        taxonomy.RepoCommunity.HPV,
    )

    assert len(result) == 2
    assert set(result) == {shared_evidence, only_sparse}


def test_gather_all_evidence_taxonomy_unsatisfiable_alone_returns_empty():
    """
    When taxonomy is the only selected mode, an unsatisfiable query no longer raises
    UnsatisfiableQueryError directly — it contributes zero evidence, and run()'s
    NoEvidenceToActOnError guard (tested separately) is what surfaces this to the user.
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    agent._gather_evidence_by_concepts = MagicMock(
        side_effect=UnsatisfiableQueryError("no matching concepts")
    )
    agent._gather_evidence_by_queries = MagicMock(return_value=[])

    result = agent._gather_all_evidence(
        UserQuery(query="test"), {SearchMode.TAXONOMY}, taxonomy.RepoCommunity.HPV
    )

    assert result == []
    agent._gather_evidence_by_queries.assert_not_called()
    mock_tui.print_info.assert_any_call(
        "[yellow]Taxonomy search couldn't be mapped to the "
        "taxonomy (no matching concepts).[/yellow]"
    )


def test_gather_all_evidence_taxonomy_unsatisfiable_with_sparse_continues():
    """
    Regression test: an unsatisfiable taxonomy search must not abort the whole run when
    sparse search is also selected — it should contribute zero evidence and sparse
    search should still run.
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    only_sparse = Evidence(destiny_id=uuid.uuid4())
    agent._gather_evidence_by_concepts = MagicMock(
        side_effect=UnsatisfiableQueryError("no matching concepts")
    )
    agent._gather_evidence_by_queries = MagicMock(return_value=[only_sparse])

    result = agent._gather_all_evidence(
        UserQuery(query="test"),
        {SearchMode.SPARSE, SearchMode.TAXONOMY},
        taxonomy.RepoCommunity.HPV,
    )

    agent._gather_evidence_by_queries.assert_called_once_with(UserQuery(query="test"))
    assert result == [only_sparse]


# ---------------------------------------------------------------------------
# dspy.Module.batch() substitutes None for individual examples that raise during
# parallel execution, rather than failing the whole batch. Every call site that
# consumes batch() results must guard against None entries in the results list.
# ---------------------------------------------------------------------------


def test_retrieve_evidence_skips_failed_batch_items():
    """
    Regression test: a query whose batch() call failed (result is None) must be
    skipped rather than crashing on `.reasoning`/`.evidence` access.
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    search_queries = [LuceneQuery(query="q1"), LuceneQuery(query="q2")]
    ok_evidence = Evidence(destiny_id=uuid.uuid4())
    ok_prediction = MagicMock(evidence=[ok_evidence], reasoning="reasoning")
    agent.evidence_retriever.batch = MagicMock(return_value=[ok_prediction, None])

    result = agent._retrieve_evidence(UserQuery(query="test"), search_queries)

    assert result == [ok_evidence]


def test_run_screening_skips_failed_batch_items():
    """Regression test: a screening batch failure must not crash `.reasoning` access."""
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    included = Evidence(destiny_id=uuid.uuid4())
    failed = Evidence(destiny_id=uuid.uuid4())
    ok_prediction = MagicMock(include=True, reasoning="reasoning")
    agent.evidence_screener.batch = MagicMock(return_value=[ok_prediction, None])
    criteria = [
        ScreeningCriterion(
            criterion_type=ScreeningCriterionType.INCLUSION, description="c1"
        )
    ]

    result = agent._run_screening(criteria, [included, failed])

    assert result == [included]


def test_generate_dimension_subtopics_raises_on_failed_batch_item():
    """
    Regression test: dimensions are a fixed-size tuple downstream, so a failed
    subtopic-generation batch item can't be silently dropped — it must raise.
    """
    agent = ResearchMappingOrchestrator()
    dimensions = (
        MappingDimension(name="d1", description="desc1"),
        MappingDimension(name="d2", description="desc2"),
        MappingDimension(name="d3", description="desc3"),
    )
    ok_prediction = MagicMock(reasoning="reasoning")
    ok_prediction.subtopics = []
    agent.subtopic_generator.batch = MagicMock(
        return_value=[ok_prediction, None, ok_prediction]
    )

    with pytest.raises(RuntimeError, match="d2"):
        agent._generate_dimension_subtopics(UserQuery(query="test"), dimensions)


def test_generate_evidence_map_skips_failed_batch_items():
    """
    Regression test for the reported crash: a mapping batch item that fails (result
    is None) must be skipped rather than raising `AttributeError` on `.reasoning`.
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    mapped = Evidence(destiny_id=uuid.uuid4())
    failed = Evidence(destiny_id=uuid.uuid4())
    ok_prediction = MagicMock(
        reasoning="reasoning",
        dimension1_subtopic="s1",
        dimension2_subtopic="s2",
        dimension3_subtopic="s3",
    )
    agent.evidence_mapper.batch = MagicMock(return_value=[ok_prediction, None])
    dimensions = (
        MappingDimensionWithSubTopics(name="d1", description="desc1", subtopics=[]),
        MappingDimensionWithSubTopics(name="d2", description="desc2", subtopics=[]),
        MappingDimensionWithSubTopics(name="d3", description="desc3", subtopics=[]),
    )

    result = agent._generate_evidence_map(
        UserQuery(query="test"), dimensions, [mapped, failed]
    )

    assert len(result) == 1
    assert result[0].evidence == mapped
    assert result[0].coordinate == {"d1": ["s1"], "d2": ["s2"], "d3": ["s3"]}


# ---------------------------------------------------------------------------
# run() must not silently proceed with an empty pipeline stage — that produces a
# confusing "0 pieces of evidence mapped" result with no indication of which stage
# dropped everything (search, screening, or mapping).
# ---------------------------------------------------------------------------


def test_run_raises_when_no_evidence_retrieved():
    agent = ResearchMappingOrchestrator()
    agent._gather_all_evidence = MagicMock(return_value=[])
    agent._screen_evidence = MagicMock()
    agent._map_evidence = MagicMock()

    with pytest.raises(NoEvidenceToActOnError, match="No evidence was retrieved"):
        agent.run(UserQuery(query="test"))

    agent._screen_evidence.assert_not_called()
    agent._map_evidence.assert_not_called()


def test_run_raises_when_all_evidence_screened_out():
    agent = ResearchMappingOrchestrator()
    agent._gather_all_evidence = MagicMock(
        return_value=[Evidence(destiny_id=uuid.uuid4())]
    )
    agent._screen_evidence = MagicMock(return_value=[])
    agent._map_evidence = MagicMock()

    with pytest.raises(NoEvidenceToActOnError, match="excluded during screening"):
        agent.run(UserQuery(query="test"))

    agent._map_evidence.assert_not_called()


def test_run_raises_when_nothing_could_be_mapped():
    agent = ResearchMappingOrchestrator()
    only_evidence = Evidence(destiny_id=uuid.uuid4())
    agent._gather_all_evidence = MagicMock(return_value=[only_evidence])
    agent._screen_evidence = MagicMock(return_value=[only_evidence])
    agent._map_evidence = MagicMock(
        return_value=EvidenceMap(
            mapped_evidence=[],
            dimensions=(
                MappingDimensionWithSubTopics(
                    name="d1", description="desc1", subtopics=[]
                ),
                MappingDimensionWithSubTopics(
                    name="d2", description="desc2", subtopics=[]
                ),
                MappingDimensionWithSubTopics(
                    name="d3", description="desc3", subtopics=[]
                ),
            ),
        )
    )

    with pytest.raises(NoEvidenceToActOnError, match="No evidence could be mapped"):
        agent.run(UserQuery(query="test"))


def test_run_returns_evidence_map_when_all_stages_succeed():
    agent = ResearchMappingOrchestrator()
    only_evidence = Evidence(destiny_id=uuid.uuid4())
    dimensions = (
        MappingDimensionWithSubTopics(name="d1", description="desc1", subtopics=[]),
        MappingDimensionWithSubTopics(name="d2", description="desc2", subtopics=[]),
        MappingDimensionWithSubTopics(name="d3", description="desc3", subtopics=[]),
    )
    expected_map = EvidenceMap(
        mapped_evidence=[
            {
                "evidence": only_evidence,
                "coordinate": {"d1": ["s1"], "d2": ["s2"], "d3": ["s3"]},
            }
        ],
        dimensions=dimensions,
    )
    agent._gather_all_evidence = MagicMock(return_value=[only_evidence])
    agent._screen_evidence = MagicMock(return_value=[only_evidence])
    agent._map_evidence = MagicMock(return_value=expected_map)

    result = agent.run(UserQuery(query="test"))

    assert result == expected_map
