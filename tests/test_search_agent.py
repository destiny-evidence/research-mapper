"""
Original end-to-end test, now marked as an integration test.
See test_integration.py for expanded live test coverage.
"""

from unittest.mock import patch

import pytest

from research_mapper.models import Evidence, UserQuery
from research_mapper.modules import SearchAgent


@pytest.mark.integration
def test_search_agent_end_to_end():
    agent = SearchAgent()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )

    with patch("research_mapper.human_in_loop.input", return_value=""):
        result = agent(query)

    assert result.evidence, "Expected at least one evidence item"
    for item in result.evidence:
        assert isinstance(item, Evidence)
