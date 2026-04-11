from unittest.mock import patch

from destiny_sdk.identifiers import IdentifierLookup

from research_mapper.models import Evidence, LuceneQuery
from research_mapper.tools import lookup_references, search_references


# ---------------------------------------------------------------------------
# search_references
# ---------------------------------------------------------------------------


def test_search_references_returns_evidence(mock_destiny_client, mock_reference):
    with patch(
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
    ):
        query = LuceneQuery(query="climate AND health")
        result = search_references(query=query)

    assert len(result) == 1
    assert isinstance(result[0], Evidence)


def test_search_references_passes_args(mock_destiny_client):
    with patch(
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
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
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
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
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
    ):
        result = search_references(query=LuceneQuery(query="climate AND health"))

    assert result == []


# ---------------------------------------------------------------------------
# lookup_references
# ---------------------------------------------------------------------------


def test_lookup_references_returns_evidence(mock_destiny_client, mock_reference):
    with patch(
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
    ):
        result = lookup_references(identifiers=["10.1000/test.doi"])

    assert len(result) == 1
    assert isinstance(result[0], Evidence)


def test_lookup_references_builds_identifier_lookup_objects(mock_destiny_client):
    with patch(
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
    ):
        lookup_references(identifiers=["10.1000/doi1", "pmid:12345"])

    call_args = mock_destiny_client.lookup.call_args[0][0]
    assert len(call_args) == 2
    assert all(isinstance(item, IdentifierLookup) for item in call_args)
    assert call_args[0].identifier == "10.1000/doi1"
    assert call_args[0].identifier_type is None
    assert call_args[1].identifier == "pmid:12345"


def test_lookup_references_empty_input(mock_destiny_client):
    mock_destiny_client.lookup.return_value = []
    with patch(
        "research_mapper.tools.get_destiny_client", return_value=mock_destiny_client
    ):
        result = lookup_references(identifiers=[])

    assert result == []
