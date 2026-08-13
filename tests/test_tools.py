from unittest.mock import MagicMock, patch

from destiny_sdk.search import AnnotationFilter

from research_mapper.models.common import Evidence
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.models.taxonomy_search import ClarificationOptions
from research_mapper.taxonomy import RepoCommunity
from research_mapper.tools.sparse_search import SearchReferencesTool, search_references
from research_mapper.tools.taxonomy_search import (
    ConceptFilterGenerationTools,
    RetrieveEvidenceByConceptsTool,
    UnsatisfiabilityTool,
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
# ConceptFilterGenerationTools
# ---------------------------------------------------------------------------


def test_ask_for_clarification_appends_unsure_option():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["A"]
    tools = ConceptFilterGenerationTools(ui=mock_ui)

    result = tools.ask_for_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    mock_ui.select_from_list.assert_called_once_with(
        ["A", "B", "I'm not sure / none of these"],
        default=[3],
    )
    assert result == ["A"]


def test_ask_for_clarification_allows_multiple_selections():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["A", "B"]
    tools = ConceptFilterGenerationTools(ui=mock_ui)

    result = tools.ask_for_clarification(
        ClarificationOptions(question="Which apply?", options=["A", "B", "C"])
    )

    assert result == ["A", "B"]


def test_ask_for_clarification_allows_unsure_alone():
    mock_ui = MagicMock()
    mock_ui.select_from_list.return_value = ["I'm not sure / none of these"]
    tools = ConceptFilterGenerationTools(ui=mock_ui)

    result = tools.ask_for_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == ["I'm not sure / none of these"]
    assert mock_ui.select_from_list.call_count == 1


def test_ask_for_clarification_rejects_unsure_combined_with_other_options():
    mock_ui = MagicMock()
    mock_ui.select_from_list.side_effect = [
        ["A", "I'm not sure / none of these"],  # invalid: mixed with a real option
        ["A"],  # corrected on retry
    ]
    tools = ConceptFilterGenerationTools(ui=mock_ui)

    result = tools.ask_for_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B"])
    )

    assert result == ["A"]
    assert mock_ui.select_from_list.call_count == 2


def test_ask_for_clarification_prints_the_question():
    mock_ui = MagicMock()
    tools = ConceptFilterGenerationTools(ui=mock_ui)

    tools.ask_for_clarification(
        ClarificationOptions(question="Which one?", options=["A"])
    )

    mock_ui.print_info.assert_called_once_with("Which one?")


def test_ask_for_clarification_defaults_to_the_unsure_option():
    """Pressing Enter with no thought must not silently pick the LLM's first option."""
    mock_ui = MagicMock()
    tools = ConceptFilterGenerationTools(ui=mock_ui)

    tools.ask_for_clarification(
        ClarificationOptions(question="Which one?", options=["A", "B", "C"])
    )

    _, kwargs = mock_ui.select_from_list.call_args
    assert kwargs["default"] == [4]  # 1-indexed; "I'm not sure" is the 4th of 4 options


# ---------------------------------------------------------------------------
# UnsatisfiabilityTool
# ---------------------------------------------------------------------------


def test_unsatisfiability_tool_starts_with_no_reason():
    tool = UnsatisfiabilityTool()
    assert tool.reason is None


def test_unsatisfiability_tool_accumulates_reason():
    tool = UnsatisfiabilityTool()

    tool.mark_unsatisfiable("No concept covers this topic.")

    assert tool.reason == "No concept covers this topic."
