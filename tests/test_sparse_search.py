from unittest.mock import MagicMock

from research_mapper.models import LuceneQuery, UserQuery
from research_mapper.modules.sparse_search import SparseQueryGenerator


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
