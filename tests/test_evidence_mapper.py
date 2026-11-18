"""EvidenceMapper against a faked Decisions API: no network, no key, no .env.

The real DecisionsEngine is used, so these also pin the request it sends and how
the API's answers become the mapper's plain coordinate.
"""

import json
import uuid

import dspy
import httpx
import pytest

from research_mapper.decisions_engine import DecisionsEngine
from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.mapping import (
    DimensionSubTopic,
    MappingDimensionWithSubTopics,
)
from research_mapper.modules.mapping import EvidenceMapper
from research_mapper.signatures.mapping import (
    mapping_along_dimensions_signature_builder,
)


def dimension(name: str, *subtopics: str) -> MappingDimensionWithSubTopics:
    return MappingDimensionWithSubTopics(
        name=name,
        description=f"{name} studied",
        subtopics=[
            DimensionSubTopic(name=sub, description=f"{sub} {name.lower()}")
            for sub in subtopics
        ],
    )


DIMENSIONS = (
    dimension("Setting", "School", "Clinic"),
    dimension("Population", "Teens", "Adults", "Older adults"),
    dimension("Outcome", "Uptake", "Adherence"),
)
QUERY = UserQuery(query="what increases HPV vaccine uptake")
EVIDENCE = Evidence(
    destiny_id=uuid.uuid4(),
    title="School-based HPV vaccination for adolescents",
    abstract="A school programme raised first-dose uptake among 12-14 year olds.",
)

# The API answers in question order, one per dimension.
CHOSEN = [
    ("School", {"School": 0.9, "Clinic": 0.1}, 0.8),
    ("Teens", {"Teens": 0.7, "Adults": 0.2, "Older adults": 0.1}, 0.6),
    ("Uptake", {"Uptake": 0.55, "Adherence": 0.45}, 0.1),
]


def decision_lm(requests: list | None = None) -> dspy.LM:
    """A decision LM whose API answers each dimension's question as in CHOSEN."""

    def answer(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(json.loads(request.content))
        answers = [
            {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": [
                    {"value": value, "probability": p}
                    for value, p in probabilities.items()
                ],
            }
            for choice, probabilities, confidence in CHOSEN
        ]
        return httpx.Response(
            200,
            json={"model": "gpt-6-luna", "answers": answers, "usage": {}},
        )

    engine = DecisionsEngine(
        "https://example.test/openai/v1",
        "key",
        timeout=5.0,
        transport=httpx.MockTransport(answer),
    )
    return dspy.LM("gpt-6-luna", engine=engine, cache=False)


@pytest.fixture(autouse=True)
def _no_settings(monkeypatch):
    """A passed-in LM must be all the mapper needs."""
    for name in ("MAPPER_LLM_MODEL", "MAPPER_LLM_BASE_URL", "MAPPER_LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_the_coordinate_is_plain_subtopic_names():
    result = EvidenceMapper(lm=decision_lm())(
        user_query=QUERY, evidence=EVIDENCE, dimensions=DIMENSIONS
    )

    assert result.dimension1_subtopic == "School"
    assert result.dimension2_subtopic == "Teens"
    assert result.dimension3_subtopic == "Uptake"
    assert result.probabilities["Population"] == CHOSEN[1][1]
    assert result.model == "gpt-6-luna"
    assert "Setting: School (90% (0.9000), confidence 80%)" in result.reasoning


def test_all_three_dimensions_go_in_one_request():
    requests: list = []
    EvidenceMapper(lm=decision_lm(requests))(
        user_query=QUERY, evidence=EVIDENCE, dimensions=DIMENSIONS
    )

    (body,) = requests
    questions = body["questions"]
    assert [q["name"] for q in questions] == [
        "dimension1_subtopic",
        "dimension2_subtopic",
        "dimension3_subtopic",
    ]
    assert all(q["type"] == "choice" for q in questions)
    # Subtopic descriptions reach the model, not just their names.
    assert questions[0]["choices"] == [
        {"value": "School", "description": "School setting"},
        {"value": "Clinic", "description": "Clinic setting"},
    ]


@pytest.mark.parametrize("subtopics", [(), ("Only one",)])
def test_a_dimension_needs_two_subtopics_to_choose_between(subtopics):
    lonely = dimension("Setting", *subtopics)

    with pytest.raises(ValueError, match="at least 2 subtopics"):
        mapping_along_dimensions_signature_builder(lonely, *DIMENSIONS[1:])

    with pytest.raises(RuntimeError, match="at least 2 subtopics"):
        EvidenceMapper(lm=decision_lm())(
            user_query=QUERY, evidence=EVIDENCE, dimensions=(lonely, *DIMENSIONS[1:])
        )


def test_duplicate_subtopic_names_are_refused():
    twins = dimension("Setting", "School", "School")

    with pytest.raises(ValueError, match="Setting"):
        mapping_along_dimensions_signature_builder(twins, *DIMENSIONS[1:])
