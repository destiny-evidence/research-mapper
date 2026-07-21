import uuid

import dspy
import pytest

from research_mapper.models import Evidence, LuceneQuery, UserQuery
from research_mapper.modules.screening import CriteriaGenerator, EvidenceScreener


@pytest.fixture(scope="module", autouse=True)
def _live(live_setup):
    pass


@pytest.mark.integration
def test_criteria_generator_with_constructed_query():
    generator = CriteriaGenerator()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )

    result = generator(user_query=query)

    assert hasattr(result, "screening_criteria")
    assert isinstance(result.screening_criteria, list)
    assert result.screening_criteria


@pytest.mark.integration
def test_evidence_screener_with_constructed_evidence():
    screener = EvidenceScreener()
    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )
    screening_criteria = CriteriaGenerator()(user_query=query).screening_criteria
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

    results = [
        screener(evidence=piece_of_evidence, screening_criteria=screening_criteria)
        for piece_of_evidence in evidence
    ]

    assert all(hasattr(result, "include") for result in results)
    assert all(isinstance(result.include, bool) for result in results)


@pytest.mark.integration
def test_evidence_screener_end_to_end_live():
    from research_mapper.tools.sparse_search import search_references

    evidence = search_references(LuceneQuery(query="climate AND health"))
    assert evidence, "Expected search to return at least one result"

    query = UserQuery(
        query="what are the best interventions to mitigate the health risks of climate change"
    )
    screening_criteria = CriteriaGenerator()(user_query=query).screening_criteria

    screener = EvidenceScreener()
    results = screener.batch(
        [
            dspy.Example(
                evidence=piece_of_evidence, screening_criteria=screening_criteria
            ).with_inputs("evidence", "screening_criteria")
            for piece_of_evidence in evidence
        ]
    )

    included = [
        piece_of_evidence
        for piece_of_evidence, result in zip(evidence, results)
        if result.include
    ]
    assert len(included) <= len(evidence)
