from unittest.mock import MagicMock, patch

from research_mapper.models import LuceneQuery, UserQuery
from research_mapper.modules.sparse_search import (
    SparseQueryGenerator,
    _fixed_search_references_builder,
)

# ---------------------------------------------------------------------------
# fixed_search_references_builder
# ---------------------------------------------------------------------------


def test_fixed_search_references_preserves_metadata():
    query = LuceneQuery(query="climate AND health")
    fn = _fixed_search_references_builder(query, {})

    assert fn.__name__ == "_search_references"
    assert fn.__doc__ is not None


def test_fixed_search_references_binds_query():
    query = LuceneQuery(query="climate AND health")
    fn = _fixed_search_references_builder(query, {})

    with patch("research_mapper.modules.search_agent.search_references") as mock_search:
        mock_search.return_value = []
        fn(start_year=2020, end_year=2024, sort=None, page=1)

    mock_search.assert_called_once_with(
        query=query,
        start_year=2020,
        end_year=2024,
        sort=None,
        page=1,
    )


def test_fixed_search_references_default_args():
    query = LuceneQuery(query="flood")
    fn = _fixed_search_references_builder(query, {})

    with patch("research_mapper.modules.search_agent.search_references") as mock_search:
        mock_search.return_value = []
        fn()

    mock_search.assert_called_once_with(
        query=query,
        start_year=None,
        end_year=None,
        sort=None,
        page=1,
    )


def test_fixed_search_references_query_cannot_be_overridden():
    """The built function accepts no 'query' parameter."""
    import inspect

    query = LuceneQuery(query="heat AND mortality")
    fn = _fixed_search_references_builder(query, {})
    params = inspect.signature(fn).parameters

    assert "query" not in params


# ---------------------------------------------------------------------------
# SearchQueryGenerator.forward (mocked ChainOfThought)
# ---------------------------------------------------------------------------


def test_search_query_generator_returns_generator_prediction():
    """SearchQueryGenerator.forward is a pure passthrough to its ChainOfThought."""
    expected_queries = [LuceneQuery(query="climate AND health")]
    mock_prediction = MagicMock()
    mock_prediction.search_queries = expected_queries

    generator = SparseQueryGenerator()
    generator.generate = MagicMock(return_value=mock_prediction)

    result = generator.forward(UserQuery(query="test"))

    generator.generate.assert_called_once()
    assert result.search_queries == expected_queries
