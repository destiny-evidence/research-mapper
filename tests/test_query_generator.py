from unittest.mock import MagicMock, patch

import pytest

from research_mapper.models import LuceneQuery, UserQuery
from research_mapper.modules.search_agent import (
    SearchAgent,
    fixed_search_references_builder,
)

# ---------------------------------------------------------------------------
# fixed_search_references_builder
# ---------------------------------------------------------------------------


def test_fixed_search_references_preserves_metadata():
    query = LuceneQuery(query="climate AND health")
    fn = fixed_search_references_builder(query, {})

    assert fn.__name__ == "_search_references"
    assert fn.__doc__ is not None


def test_fixed_search_references_binds_query():
    query = LuceneQuery(query="climate AND health")
    fn = fixed_search_references_builder(query, {})

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
    fn = fixed_search_references_builder(query, {})

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
    fn = fixed_search_references_builder(query, {})
    params = inspect.signature(fn).parameters

    assert "query" not in params


# ---------------------------------------------------------------------------
# SearchAgent.forward — query generation (mocked ChainOfThought)
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_agent_forward():
    """
    Patch the query_generator call on a SearchAgent instance to return
    a predictable set of LuceneQuery objects, bypassing the LLM entirely.
    Also patches validate_search_queries and the ReAct agent loop.
    """
    expected_queries = [LuceneQuery(query="climate AND health")]

    agent = SearchAgent()

    mock_prediction = MagicMock()
    mock_prediction.search_queries = expected_queries
    agent.query_generator = MagicMock(return_value=mock_prediction)

    return agent, expected_queries


def test_forward_deduplicates_evidence(patched_agent_forward):
    """Evidence returned from multiple queries is deduplicated."""
    import uuid
    from research_mapper.models import Evidence

    agent, expected_queries = patched_agent_forward

    shared_id = uuid.uuid4()
    shared_evidence = Evidence(destiny_id=shared_id)

    two_queries = [LuceneQuery(query="q1"), LuceneQuery(query="q2")]
    agent.query_generator.return_value.search_queries = two_queries

    async def mock_semaphore(fn, *args, **kwargs):
        return [shared_evidence]

    with patch("research_mapper.modules.search_agent.run_with_semaphore", side_effect=mock_semaphore):
        result = agent.forward(UserQuery(query="test"))

    assert len(result.evidence) == 1
