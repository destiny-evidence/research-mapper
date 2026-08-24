from unittest.mock import patch

import pytest
from destiny_sdk.search import AnnotationFilter

from research_mapper.models.common import Evidence
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.models.taxonomy_search import ClarificationOptions
from research_mapper.taxonomy import RepoCommunity
from research_mapper.tools.sparse_search import SearchReferencesTool, search_references
from research_mapper.tools.taxonomy_search import (
    RetrieveEvidenceByConceptsTool,
    ask_for_clarification,
    mark_unsatisfiable,
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
