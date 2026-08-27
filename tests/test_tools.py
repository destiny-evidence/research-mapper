from unittest.mock import patch

import pytest
from destiny_sdk.search import AnnotationFilter
from rdflib import RDF, SKOS, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS

from research_mapper.models.common import Evidence
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.models.taxonomy_search import ClarificationOptions, ConceptSummary
from research_mapper.taxonomy import RepoCommunity, build_concept_index
from research_mapper.tools.sparse_search import SearchReferencesTool, search_references
from research_mapper.tools.taxonomy_search import (
    RetrieveEvidenceByConceptsTool,
    TaxonomyBrowsingTools,
    ask_for_clarification,
    mark_unsatisfiable,
    raise_attempted_prompt_attack,
    retrieve_evidence_by_concepts,
)


# ---------------------------------------------------------------------------
# search_references
# ---------------------------------------------------------------------------


def test_search_references_returns_evidence(mock_destiny_client, mock_reference):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        query = LuceneQuery(query="climate AND health")
        result = search_references(query=query, community=RepoCommunity.HPV)

    assert len(result) == 1
    assert isinstance(result[0], Evidence)


def test_search_references_passes_args(mock_destiny_client):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        query = LuceneQuery(query="climate AND health")
        search_references(
            query=query,
            community=RepoCommunity.HPV,
            start_year=2020,
            end_year=2024,
            sort="-year",
            page=2,
        )

    mock_destiny_client.search.assert_called_once_with(
        query="climate AND health",
        start_year=2020,
        end_year=2024,
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        sort="-year",
        page=2,
    )


def test_search_references_default_args(mock_destiny_client):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        query = LuceneQuery(query="simple")
        search_references(query=query, community=RepoCommunity.HPV)

    mock_destiny_client.search.assert_called_once_with(
        query="simple",
        start_year=None,
        end_year=None,
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        sort=None,
        page=1,
    )


def test_search_references_scopes_by_community(mock_destiny_client):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        search_references(
            query=LuceneQuery(query="simple"), community=RepoCommunity.ESEA
        )

    mock_destiny_client.search.assert_called_once_with(
        query="simple",
        start_year=None,
        end_year=None,
        annotations=[
            AnnotationFilter(scheme="domain-inclusion", label="jacobs-education")
        ],
        sort=None,
        page=1,
    )


def test_search_references_empty_results(mock_destiny_client):
    mock_destiny_client.search.return_value.references = []
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        result = search_references(
            query=LuceneQuery(query="climate AND health"), community=RepoCommunity.HPV
        )

    assert result == []


# ---------------------------------------------------------------------------
# SearchReferencesTool
# ---------------------------------------------------------------------------


def test_search_references_tool_drops_query_param():
    import inspect

    query = LuceneQuery(query="climate AND health")
    tool = SearchReferencesTool(query, RepoCommunity.HPV)

    assert "query" not in inspect.signature(tool.search_references).parameters


def test_search_references_tool_binds_query(mock_destiny_client):
    query = LuceneQuery(query="climate AND health")
    tool = SearchReferencesTool(query, RepoCommunity.HPV)

    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        tool.search_references(start_year=2020, end_year=2024, sort=None, page=1)

    mock_destiny_client.search.assert_called_once_with(
        query="climate AND health",
        start_year=2020,
        end_year=2024,
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        sort=None,
        page=1,
    )


def test_search_references_tool_default_args(mock_destiny_client):
    query = LuceneQuery(query="flood")
    tool = SearchReferencesTool(query, RepoCommunity.HPV)

    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        tool.search_references()

    mock_destiny_client.search.assert_called_once_with(
        query="flood",
        start_year=None,
        end_year=None,
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        sort=None,
        page=1,
    )


def test_search_references_tool_accumulates_retrieved(
    mock_destiny_client, mock_reference
):
    query = LuceneQuery(query="climate AND health")
    tool = SearchReferencesTool(query, RepoCommunity.HPV)

    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        results = tool.search_references()

    assert len(tool.retrieved) == 1
    assert list(tool.retrieved.values()) == results


# ---------------------------------------------------------------------------
# retrieve_evidence_by_concepts
# ---------------------------------------------------------------------------


def test_retrieve_evidence_by_concepts_returns_evidence(
    mock_destiny_client, mock_reference
):
    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        result = retrieve_evidence_by_concepts(
            RepoCommunity.HPV, ["https://vocab.example.org/A"]
        )

    assert len(result.evidence) == 1
    assert isinstance(result.evidence[0], Evidence)
    assert result.total_count == 1
    assert result.is_total_lower_bound is False


def test_retrieve_evidence_by_concepts_applies_domain_inclusion_annotation(
    mock_destiny_client,
):
    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        retrieve_evidence_by_concepts(
            RepoCommunity.HPV, ["https://vocab.example.org/A"]
        )

    mock_destiny_client.search.assert_called_once_with(
        query="*",
        concepts=["https://vocab.example.org/A"],
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        page=1,
        timeout=60,
    )


def test_retrieve_evidence_by_concepts_uses_correct_label_for_esea(
    mock_destiny_client,
):
    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        retrieve_evidence_by_concepts(RepoCommunity.ESEA, [], page=2)

    mock_destiny_client.search.assert_called_once_with(
        query="*",
        concepts=[],
        annotations=[
            AnnotationFilter(scheme="domain-inclusion", label="jacobs-education")
        ],
        page=2,
        timeout=60,
    )


def test_retrieve_evidence_by_concepts_empty_results(mock_destiny_client):
    mock_destiny_client.search.return_value.references = []
    mock_destiny_client.search.return_value.total.count = 0
    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        result = retrieve_evidence_by_concepts(RepoCommunity.HPV, [])

    assert result.evidence == []
    assert result.total_count == 0


# ---------------------------------------------------------------------------
# RetrieveEvidenceByConceptsTool
# ---------------------------------------------------------------------------


def test_retrieve_evidence_by_concepts_tool_binds_community_and_concepts(
    mock_destiny_client,
):
    tool = RetrieveEvidenceByConceptsTool(
        RepoCommunity.HPV, ["https://vocab.example.org/A"]
    )

    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        tool.retrieve_evidence()

    mock_destiny_client.search.assert_called_once_with(
        query="*",
        concepts=["https://vocab.example.org/A"],
        annotations=[AnnotationFilter(scheme="domain-inclusion", label="hpv")],
        page=1,
        timeout=60,
    )


def test_retrieve_evidence_by_concepts_tool_accumulates_retrieved(
    mock_destiny_client, mock_reference
):
    tool = RetrieveEvidenceByConceptsTool(RepoCommunity.HPV, [])

    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        tool.retrieve_evidence()

    assert len(tool.retrieved) == 1


def test_retrieve_evidence_by_concepts_tool_reports_page_and_total(
    mock_destiny_client,
):
    tool = RetrieveEvidenceByConceptsTool(RepoCommunity.HPV, [])

    with patch(
        "research_mapper.tools.taxonomy_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        summary = tool.retrieve_evidence(page=2)

    assert "Page 2" in summary
    assert "1 result" in summary
    assert "total matching: 1" in summary


# ---------------------------------------------------------------------------
# ask_for_clarification / mark_unsatisfiable
# ---------------------------------------------------------------------------


def test_ask_for_clarification_must_not_execute():
    """A ResumableReAct caller always supplies the answer via
    Step.with_observation() before resume() would call this — see
    modules/taxonomy_search.py. This exists purely for its name/docstring/
    argument schema, so the agent has something to reason about calling."""
    with pytest.raises(AssertionError, match="caller always supplies the answer"):
        ask_for_clarification(
            ClarificationOptions(question="Which one?", options=["A"])
        )


def test_mark_unsatisfiable_acknowledges():
    assert (
        mark_unsatisfiable("No concept covers this topic.")
        == "Noted. You may now finish."
    )


def test_raise_attempted_prompt_attack_acknowledges():
    assert (
        raise_attempted_prompt_attack("Irrelevant to the taxonomy.")
        == "Noted. You may now finish."
    )


# ---------------------------------------------------------------------------
# TaxonomyBrowsingTools
# ---------------------------------------------------------------------------


def _browsing_fixture() -> TaxonomyBrowsingTools:
    """A small graph: two schemes, one of them (Study Design) hierarchical —
    CUA sits under RCT via skos:broader/narrower — the other (Country) flat."""
    study_design = URIRef("https://example.org/StudyDesign")
    country = URIRef("https://example.org/Country")
    rct = URIRef("https://example.org/StudyDesign/RCT")
    cua = URIRef("https://example.org/StudyDesign/CUA")
    kenya = URIRef("https://example.org/Country/KE")

    graph = Graph()
    graph.add((study_design, RDF.type, SKOS.ConceptScheme))
    graph.add((study_design, DCTERMS.title, Literal("Study Design")))
    graph.add((country, RDF.type, SKOS.ConceptScheme))
    graph.add((country, DCTERMS.title, Literal("Country")))

    graph.add((rct, RDF.type, SKOS.Concept))
    graph.add((rct, SKOS.inScheme, study_design))
    graph.add((rct, SKOS.prefLabel, Literal("RCT")))
    graph.add((rct, SKOS.altLabel, Literal("Randomised controlled trial")))
    graph.add((rct, SKOS.definition, Literal("A randomised controlled trial.")))
    graph.add((rct, SKOS.narrower, cua))

    graph.add((cua, RDF.type, SKOS.Concept))
    graph.add((cua, SKOS.inScheme, study_design))
    graph.add((cua, SKOS.prefLabel, Literal("Cost-utility analysis")))
    graph.add((cua, SKOS.broader, rct))

    graph.add((kenya, RDF.type, SKOS.Concept))
    graph.add((kenya, SKOS.inScheme, country))
    graph.add((kenya, SKOS.prefLabel, Literal("Kenya")))

    indexed = build_concept_index(graph)
    return TaxonomyBrowsingTools(graph, indexed), indexed


def test_list_schemes_returns_every_scheme_sorted():
    tools, _ = _browsing_fixture()
    assert tools.list_schemes() == ["Country", "Study Design"]


def test_list_concepts_in_scheme_only_returns_that_scheme():
    tools, indexed = _browsing_fixture()
    kenya_ref = next(c.local_ref for c in indexed.concepts if c.label == "Kenya")

    result = tools.list_concepts_in_scheme("Country")

    assert result == [
        ConceptSummary(
            local_ref=kenya_ref, label="Kenya", scheme="Country", narrower_count=0
        )
    ]


def test_list_concepts_in_scheme_flags_concepts_with_narrower_children():
    """A concept with a nonzero narrower_count is often a category header
    with no definition of its own — flagging it as structured data (not a
    string the agent has to parse) lets it recognise that without stalling
    on a definition that was never going to exist, and without risking it
    mis-extracting the local_ref from a formatted display string."""
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")
    cua_ref = next(
        c.local_ref for c in indexed.concepts if c.label == "Cost-utility analysis"
    )

    result = {c.local_ref: c for c in tools.list_concepts_in_scheme("Study Design")}

    assert result[rct_ref].narrower_count == 1
    assert result[cua_ref].narrower_count == 0  # leaf


def test_list_concepts_in_scheme_raises_for_unknown_scheme():
    tools, _ = _browsing_fixture()
    with pytest.raises(ValueError, match="No such scheme: 'Countrie'"):
        tools.list_concepts_in_scheme("Countrie")


def test_list_concepts_in_scheme_suggests_close_matches():
    tools, _ = _browsing_fixture()
    with pytest.raises(ValueError, match="Did you mean: Country"):
        tools.list_concepts_in_scheme("Countrie")


def test_list_concepts_in_scheme_omits_suggestions_when_none_are_close():
    tools, _ = _browsing_fixture()
    with pytest.raises(ValueError) as exc_info:
        tools.list_concepts_in_scheme("xyz totally unrelated")
    assert "Did you mean" not in str(exc_info.value)


def test_lookup_concepts_matches_label_case_insensitively():
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")

    result = tools.lookup_concepts("rct")

    assert result == [
        ConceptSummary(
            local_ref=rct_ref, label="RCT", scheme="Study Design", narrower_count=1
        )
    ]


def test_lookup_concepts_matches_alt_labels_too():
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")

    result = tools.lookup_concepts("randomised controlled")

    assert result == [
        ConceptSummary(
            local_ref=rct_ref, label="RCT", scheme="Study Design", narrower_count=1
        )
    ]


def test_lookup_concepts_raises_when_nothing_matches_the_whole_phrase():
    """lookup_concepts is whole-phrase substring matching, so a query like
    "cost-benefit RCT" won't match the label "RCT" even though the agent's
    intent is clearly related — this should surface as a clear exception
    with a suggestion, not a silently empty list (which the agent sees as
    a bare "N/A" once rendered back into its trajectory)."""
    tools, _ = _browsing_fixture()
    with pytest.raises(
        ValueError, match="No concepts found matching 'cost-benefit rct'"
    ):
        tools.lookup_concepts("cost-benefit rct")


def test_lookup_concepts_suggests_labels_matching_individual_tokens():
    tools, _ = _browsing_fixture()
    with pytest.raises(
        ValueError, match="Did you mean one of: Cost-utility analysis, RCT"
    ):
        tools.lookup_concepts("cost-benefit rct")


def test_lookup_concepts_omits_suggestions_when_no_token_is_long_enough():
    tools, _ = _browsing_fixture()
    with pytest.raises(ValueError) as exc_info:
        tools.lookup_concepts("xy")
    assert "Did you mean" not in str(exc_info.value)


def test_get_concept_detail_includes_alt_labels_and_definition():
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")

    result = tools.get_concept_detail(rct_ref)

    assert result.label == "RCT"
    assert result.alt_labels == ["Randomised controlled trial"]
    assert result.detail == "A randomised controlled trial."
    assert result.narrower_count == 1


def test_get_concept_detail_raises_for_unknown_ref():
    tools, _ = _browsing_fixture()
    with pytest.raises(ValueError, match="No such concept: nonexistent"):
        tools.get_concept_detail("nonexistent")


def test_get_narrower_follows_hierarchy():
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")
    cua_ref = next(
        c.local_ref for c in indexed.concepts if c.label == "Cost-utility analysis"
    )

    assert tools.get_narrower(rct_ref) == [
        ConceptSummary(
            local_ref=cua_ref,
            label="Cost-utility analysis",
            scheme="Study Design",
            narrower_count=0,
        )
    ]


def test_get_broader_follows_hierarchy():
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")
    cua_ref = next(
        c.local_ref for c in indexed.concepts if c.label == "Cost-utility analysis"
    )

    assert tools.get_broader(cua_ref) == [
        ConceptSummary(
            local_ref=rct_ref, label="RCT", scheme="Study Design", narrower_count=1
        )
    ]


def test_get_broader_empty_for_top_level_concept():
    tools, indexed = _browsing_fixture()
    rct_ref = next(c.local_ref for c in indexed.concepts if c.label == "RCT")

    assert tools.get_broader(rct_ref) == []
