import uuid
from unittest.mock import patch

import pytest

from research_mapper.models import Evidence, LuceneQuery, UserQuery
from research_mapper.modules.screening_agent import ScreeningAgent


@pytest.fixture(scope="module", autouse=True)
def _live(live_setup):
    pass


@pytest.mark.integration
def test_screening_agent_with_constructed_evidence():
    agent = ScreeningAgent()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )
    evidence = [
        Evidence(
            destiny_id=uuid.uuid4(),
            title="Heat stress and cardiovascular mortality: a systematic review",
            abstract="This review examines interventions that reduce cardiovascular death due to heat exposure in urban populations, including cooling centres and early warning systems.",
            authors=["Smith J", "Jones K"],
            year=2022,
        ),
        Evidence(
            destiny_id=uuid.uuid4(),
            title="Medieval cooking techniques in Northern Europe",
            abstract="A historical analysis of food preparation methods used in 12th-century monasteries, focusing on the use of open hearths and clay pots.",
            authors=["Brown A"],
            year=2019,
        ),
    ]

    with patch("research_mapper.human_in_loop.input", return_value=""):
        result = agent.forward(query, evidence)

    assert hasattr(result, "screened_evidence")
    assert isinstance(result.screened_evidence, list)
    assert len(result.screened_evidence) <= len(evidence)
    for item in result.screened_evidence:
        assert isinstance(item, Evidence)


@pytest.mark.integration
def test_screening_agent_end_to_end_live():
    from research_mapper.tools import search_references

    evidence = search_references(LuceneQuery(query="climate AND health"))
    assert evidence, "Expected search to return at least one result"

    agent = ScreeningAgent()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )

    with patch("research_mapper.human_in_loop.input", return_value=""):
        result = agent.forward(query, evidence)

    assert hasattr(result, "screened_evidence")
    assert isinstance(result.screened_evidence, list)
    assert len(result.screened_evidence) <= len(evidence)
    for item in result.screened_evidence:
        assert isinstance(item, Evidence)
        assert item.destiny_id
