"""
Integration tests — require a live .env with real credentials.

Run with:
    pytest -m integration

Skip in CI with:
    pytest -m "not integration"
"""

import uuid
from unittest.mock import patch

import pytest
from destiny_sdk.identifiers import OpenAlexIdentifier
from dotenv import load_dotenv

from research_mapper.models import Evidence, LuceneQuery, UserQuery


@pytest.fixture(scope="module", autouse=True)
def live_setup():
    """Load .env and configure DSPy + DESTINY client once per module."""
    import os

    load_dotenv()

    required = [
        "DESTINY_BASE_URL",
        "DESTINY_AZURE_CLIENT_ID",
        "DESTINY_AZURE_LOGIN_URL",
        "DESTINY_AZURE_APPLICATION_ID",
        "DESTINY_SEARCH_ENDPOINT",
        "LLM_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        pytest.skip(f"Missing env vars: {missing}")

    from research_mapper.config import configure_dspy
    from research_mapper.utils import get_destiny_client

    configure_dspy()
    get_destiny_client.cache_clear()


# ---------------------------------------------------------------------------
# Tool-level integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_search_references_tool_live():
    from research_mapper.tools import search_references

    query = LuceneQuery(query="climate AND health")
    results = search_references(query=query)

    assert isinstance(results, list)
    assert len(results) > 0, "Expected at least one result for a broad query"
    for item in results:
        assert isinstance(item, Evidence)
        assert item.destiny_id, "Evidence item should have a non-empty id"


@pytest.mark.integration
def test_search_references_tool_live_with_year_filter():
    from research_mapper.tools import search_references

    query = LuceneQuery(query="heat AND mortality")
    results = search_references(query=query, start_year=2020, end_year=2024)

    assert isinstance(results, list)
    for item in results:
        if item.year is not None:
            assert 2020 <= item.year <= 2024, (
                f"Year {item.year} outside requested range"
            )


@pytest.mark.integration
def test_search_references_tool_live_pagination():
    from research_mapper.tools import search_references

    query = LuceneQuery(query="climate AND health")
    page1 = search_references(query=query, page=1)
    page2 = search_references(query=query, page=2)

    ids_page1 = {item.destiny_id for item in page1}
    ids_page2 = {item.destiny_id for item in page2}
    assert ids_page1 - ids_page2, "Pages should not overlap"


@pytest.mark.integration
def test_lookup_references_tool_with_destiny_id_live():
    """Look up a reference by DOI and verify it returns an Evidence object."""
    from research_mapper.tools import lookup_references

    test_destiny_id = uuid.UUID("ce0d0782-59b7-4e3f-8719-293a748681a9")
    results = lookup_references(identifiers=[test_destiny_id])

    assert isinstance(results, list)
    assert len(results) >= 1, f"Expected to find reference for DOI {test_destiny_id}"
    assert isinstance(results[0], Evidence)
    assert results[0].destiny_id


@pytest.mark.integration
def test_lookup_references_tool_with_external_id_live():
    """Look up a reference by DOI and verify it returns an Evidence object."""
    from research_mapper.tools import lookup_references

    test_open_alex_id = OpenAlexIdentifier(
        identifier="W3087468654", identifier_type="open_alex"
    )
    results = lookup_references(identifiers=[test_open_alex_id])

    assert isinstance(results, list)
    assert len(results) >= 1, f"Expected to find reference for DOI {test_open_alex_id}"
    assert isinstance(results[0], Evidence)
    assert results[0].destiny_id


# ---------------------------------------------------------------------------
# Full agent integration test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_search_agent_end_to_end_live():
    from research_mapper.modules import SearchAgent

    agent = SearchAgent()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )

    with patch("research_mapper.human_in_loop.input", return_value=""):
        result = agent(query)

    assert result.evidence, "Expected at least one evidence item"
    for item in result.evidence:
        assert isinstance(item, Evidence)
        assert item.destiny_id, "Evidence should have a non-empty id"
