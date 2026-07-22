from unittest.mock import patch

from research_mapper.models.common import Evidence
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.tools.sparse_search import SearchReferencesTool, search_references


# ---------------------------------------------------------------------------
# search_references
# ---------------------------------------------------------------------------


def test_search_references_returns_evidence(mock_destiny_client, mock_reference):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        query = LuceneQuery(query="climate AND health")
        result = search_references(query=query)

    assert len(result) == 1
    assert isinstance(result[0], Evidence)


def test_search_references_passes_args(mock_destiny_client):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        query = LuceneQuery(query="climate AND health")
        search_references(
            query=query, start_year=2020, end_year=2024, sort="-year", page=2
        )

    mock_destiny_client.search.assert_called_once_with(
        query="climate AND health",
        start_year=2020,
        end_year=2024,
        annotations=None,
        sort="-year",
        page=2,
    )


def test_search_references_default_args(mock_destiny_client):
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        query = LuceneQuery(query="simple")
        search_references(query=query)

    mock_destiny_client.search.assert_called_once_with(
        query="simple",
        start_year=None,
        end_year=None,
        annotations=None,
        sort=None,
        page=1,
    )


def test_search_references_empty_results(mock_destiny_client):
    mock_destiny_client.search.return_value.references = []
    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        result = search_references(query=LuceneQuery(query="climate AND health"))

    assert result == []


# ---------------------------------------------------------------------------
# SearchReferencesTool
# ---------------------------------------------------------------------------


def test_search_references_tool_drops_query_param():
    import inspect

    query = LuceneQuery(query="climate AND health")
    tool = SearchReferencesTool(query)

    assert "query" not in inspect.signature(tool.search_references).parameters


def test_search_references_tool_binds_query(mock_destiny_client):
    query = LuceneQuery(query="climate AND health")
    tool = SearchReferencesTool(query)

    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        tool.search_references(start_year=2020, end_year=2024, sort=None, page=1)

    mock_destiny_client.search.assert_called_once_with(
        query="climate AND health",
        start_year=2020,
        end_year=2024,
        annotations=None,
        sort=None,
        page=1,
    )


def test_search_references_tool_default_args(mock_destiny_client):
    query = LuceneQuery(query="flood")
    tool = SearchReferencesTool(query)

    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        tool.search_references()

    mock_destiny_client.search.assert_called_once_with(
        query="flood",
        start_year=None,
        end_year=None,
        annotations=None,
        sort=None,
        page=1,
    )


def test_search_references_tool_accumulates_retrieved(
    mock_destiny_client, mock_reference
):
    query = LuceneQuery(query="climate AND health")
    tool = SearchReferencesTool(query)

    with patch(
        "research_mapper.tools.sparse_search.get_destiny_client",
        return_value=mock_destiny_client,
    ):
        results = tool.search_references()

    assert len(tool.retrieved) == 1
    assert list(tool.retrieved.values()) == results
