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
    MappingMode,
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

    result = agent._retrieve_evidence(
        UserQuery(query="test"), search_queries, taxonomy.RepoCommunity.HPV
    )

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

    call_kwargs = agent.concept_filter_generator.call_args.kwargs
    assert call_kwargs["user_query"] == UserQuery(query="test")
    assert call_kwargs["indexed"] == indexed
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

    agent._gather_evidence_by_queries.assert_called_once_with(
        UserQuery(query="test"), taxonomy.RepoCommunity.HPV
    )
    agent._gather_evidence_by_concepts.assert_not_called()


def test_gather_all_evidence_sparse_only():
    agent = ResearchMappingOrchestrator()
    agent._gather_evidence_by_queries = MagicMock(return_value=[])
    agent._gather_evidence_by_concepts = MagicMock(return_value=[])

    agent._gather_all_evidence(
        UserQuery(query="test"), {SearchMode.SPARSE}, taxonomy.RepoCommunity.HPV
    )

    agent._gather_evidence_by_queries.assert_called_once_with(
        UserQuery(query="test"), taxonomy.RepoCommunity.HPV
    )
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

    agent._gather_evidence_by_queries.assert_called_once_with(
        UserQuery(query="test"), taxonomy.RepoCommunity.HPV
    )
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

    result = agent._retrieve_evidence(
        UserQuery(query="test"), search_queries, taxonomy.RepoCommunity.HPV
    )

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


# ---------------------------------------------------------------------------
# _map_evidence — dispatches to the taxonomy-scheme or suggested-dimensions path by
# mapping_mode; _map_evidence_via_taxonomy maps evidence directly from its known
# taxonomy concepts, dropping (and reporting on) evidence that isn't annotated
# against every chosen scheme, with no LLM fallback.
# ---------------------------------------------------------------------------


def _taxonomy_indexed_vocab() -> IndexedVocab:
    concepts = [
        Concept(local_ref="C0", scheme="Country", label="Kenya"),
        Concept(local_ref="C1", scheme="Country", label="Uganda"),
        Concept(local_ref="C2", scheme="Study Design", label="RCT"),
        Concept(local_ref="C3", scheme="Study Design", label="Cohort"),
        Concept(local_ref="C4", scheme="Outcome", label="Mortality"),
        Concept(local_ref="C5", scheme="Outcome", label="Morbidity"),
    ]
    local_ref_to_iri = {
        c.local_ref: f"https://vocab.example.org/{c.local_ref}" for c in concepts
    }
    return IndexedVocab(concepts=concepts, local_ref_to_iri=local_ref_to_iri)


def test_map_evidence_dispatches_to_taxonomy_path():
    agent = ResearchMappingOrchestrator()
    agent._map_evidence_via_taxonomy = MagicMock(return_value="taxonomy_result")
    agent._map_evidence_via_suggested_dimensions = MagicMock()

    result = agent._map_evidence(
        UserQuery(query="test"), [], MappingMode.TAXONOMY, taxonomy.RepoCommunity.HPV
    )

    assert result == "taxonomy_result"
    agent._map_evidence_via_taxonomy.assert_called_once_with(
        UserQuery(query="test"), [], taxonomy.RepoCommunity.HPV
    )
    agent._map_evidence_via_suggested_dimensions.assert_not_called()


def test_map_evidence_dispatches_to_suggested_dimensions_path_by_default():
    agent = ResearchMappingOrchestrator()
    agent._map_evidence_via_taxonomy = MagicMock()
    agent._map_evidence_via_suggested_dimensions = MagicMock(
        return_value="suggested_result"
    )

    result = agent._map_evidence(
        UserQuery(query="test"), [], MappingMode.SUGGESTED, taxonomy.RepoCommunity.HPV
    )

    assert result == "suggested_result"
    agent._map_evidence_via_taxonomy.assert_not_called()


def test_map_evidence_via_taxonomy_falls_back_when_fewer_than_3_schemes_represented():
    """Only 'Country' is represented in the evidence's known concepts — fewer than the
    3 schemes needed for taxonomy-scheme mapping, so it falls back to suggested
    dimensions instead of failing outright."""
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    evidence = [
        Evidence(
            destiny_id=uuid.uuid4(),
            known_concepts=["https://vocab.example.org/C0"],
        )
    ]
    agent._map_evidence_via_suggested_dimensions = MagicMock(
        return_value="fallback_result"
    )

    with (
        patch.object(taxonomy, "get_taxonomy", return_value={}),
        patch.object(
            taxonomy, "build_concept_index", return_value=_taxonomy_indexed_vocab()
        ),
    ):
        result = agent._map_evidence_via_taxonomy(
            UserQuery(query="test"), evidence, taxonomy.RepoCommunity.HPV
        )

    assert result == "fallback_result"
    agent._map_evidence_via_suggested_dimensions.assert_called_once_with(
        UserQuery(query="test"), evidence
    )
    mock_tui.print_info.assert_any_call(
        "[yellow]Fewer than 3 taxonomy schemes are represented in this "
        "evidence — falling back to suggested mapping dimensions.[/yellow]"
    )


def test_map_evidence_via_taxonomy_maps_drops_and_reports():
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    indexed = _taxonomy_indexed_vocab()

    fully_annotated = Evidence(
        destiny_id=uuid.uuid4(),
        known_concepts=[
            "https://vocab.example.org/C0",  # Kenya - Country
            "https://vocab.example.org/C2",  # RCT - Study Design
            "https://vocab.example.org/C4",  # Mortality - Outcome
        ],
    )
    multi_concept = Evidence(
        destiny_id=uuid.uuid4(),
        known_concepts=[
            "https://vocab.example.org/C0",  # Kenya - Country
            "https://vocab.example.org/C1",  # Uganda - Country (2nd match, same dim)
            "https://vocab.example.org/C3",  # Cohort - Study Design
            "https://vocab.example.org/C5",  # Morbidity - Outcome
        ],
    )
    unannotated = Evidence(
        destiny_id=uuid.uuid4(),
        known_concepts=["https://vocab.example.org/C0"],  # missing Study Design/Outcome
    )

    dimensions = (
        MappingDimensionWithSubTopics(name="Country", description="", subtopics=[]),
        MappingDimensionWithSubTopics(
            name="Study Design", description="", subtopics=[]
        ),
        MappingDimensionWithSubTopics(name="Outcome", description="", subtopics=[]),
    )
    prediction = MagicMock(
        dimension1=dimensions[0],
        dimension2=dimensions[1],
        dimension3=dimensions[2],
        reasoning="some reasoning",
    )
    agent.taxonomy_scheme_dimension_generator = MagicMock(return_value=prediction)

    with (
        patch.object(taxonomy, "get_taxonomy", return_value={}),
        patch.object(taxonomy, "build_concept_index", return_value=indexed),
    ):
        result = agent._map_evidence_via_taxonomy(
            UserQuery(query="test"),
            [fully_annotated, multi_concept, unannotated],
            taxonomy.RepoCommunity.HPV,
        )

    assert len(result.mapped_evidence) == 2
    mapped_by_id = {m.evidence.destiny_id: m for m in result.mapped_evidence}
    assert mapped_by_id[fully_annotated.destiny_id].coordinate == {
        "Country": ["Kenya"],
        "Study Design": ["RCT"],
        "Outcome": ["Mortality"],
    }
    assert mapped_by_id[multi_concept.destiny_id].coordinate == {
        "Country": ["Kenya", "Uganda"],
        "Study Design": ["Cohort"],
        "Outcome": ["Morbidity"],
    }
    assert unannotated.destiny_id not in mapped_by_id
    mock_tui.print_info.assert_any_call(
        "2 piece(s) of evidence mapped via taxonomy schemes; 1 dropped — not "
        "annotated against all of the chosen schemes."
    )


def test_run_raises_when_taxonomy_mapping_drops_all_evidence():
    """
    Regression test: if every piece of screened evidence gets dropped during taxonomy
    mapping (none annotated against all 3 chosen schemes), run() must still raise
    NoEvidenceToActOnError rather than returning/rendering an empty map — the same
    generic empty-mapped_evidence guard used for the suggested-dimensions path.
    """
    mock_tui = MagicMock()
    agent = ResearchMappingOrchestrator(tui=mock_tui)
    indexed = _taxonomy_indexed_vocab()

    # Each item only carries a concept from a single scheme — the union across items
    # covers all 3 schemes (so taxonomy mapping proceeds), but no single item is
    # annotated against every chosen scheme, so all 3 are dropped.
    only_country = Evidence(
        destiny_id=uuid.uuid4(), known_concepts=["https://vocab.example.org/C0"]
    )
    only_study_design = Evidence(
        destiny_id=uuid.uuid4(), known_concepts=["https://vocab.example.org/C2"]
    )
    only_outcome = Evidence(
        destiny_id=uuid.uuid4(), known_concepts=["https://vocab.example.org/C4"]
    )
    evidence = [only_country, only_study_design, only_outcome]

    agent._gather_all_evidence = MagicMock(return_value=evidence)
    agent._screen_evidence = MagicMock(return_value=evidence)
    agent._select_mapping_mode = MagicMock(return_value=MappingMode.TAXONOMY)

    dimensions = (
        MappingDimensionWithSubTopics(name="Country", description="", subtopics=[]),
        MappingDimensionWithSubTopics(
            name="Study Design", description="", subtopics=[]
        ),
        MappingDimensionWithSubTopics(name="Outcome", description="", subtopics=[]),
    )
    prediction = MagicMock(
        dimension1=dimensions[0],
        dimension2=dimensions[1],
        dimension3=dimensions[2],
        reasoning="some reasoning",
    )
    agent.taxonomy_scheme_dimension_generator = MagicMock(return_value=prediction)

    with (
        patch.object(taxonomy, "get_taxonomy", return_value={}),
        patch.object(taxonomy, "build_concept_index", return_value=indexed),
        pytest.raises(NoEvidenceToActOnError, match="No evidence could be mapped"),
    ):
        agent.run(UserQuery(query="test"))
