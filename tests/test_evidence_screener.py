"""EvidenceScreener against a faked Decisions API: no network, no key, no .env.

The real DecisionsEngine is used, so these also pin the request it sends and how
the API's answer becomes the screener's plain outputs.
"""

import json
import uuid

import dspy
import httpx
import pytest

from research_mapper.decisions_engine import DecisionsEngine
from research_mapper.models.common import Evidence
from research_mapper.models.screening import ScreeningCriterion, ScreeningCriterionType
from research_mapper.modules.screening import EvidenceScreener

EVIDENCE = Evidence(
    destiny_id=uuid.uuid4(),
    title="Heat stress and cardiovascular mortality: a systematic review",
    abstract="Cooling centres and early warning systems reduce heat deaths.",
)
CRITERIA = [
    ScreeningCriterion(
        criterion_type=ScreeningCriterionType.INCLUSION,
        description="Interventions for climate-related health risks",
    )
]


def decision_lm(probability: float, requests: list | None = None) -> dspy.LM:
    """A decision LM whose API answers every question with `probability`."""

    def answer(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "answers": [{"type": "predicate", "probability": probability}],
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
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
    """A passed-in LM must be all the screener needs."""
    for name in ("MAPPER_LLM_MODEL", "MAPPER_LLM_BASE_URL", "MAPPER_LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("probability", "include"),
    [(0.83, True), (0.12, False)],
)
def test_outputs_are_plain_values(probability, include):
    result = EvidenceScreener(lm=decision_lm(probability))(
        evidence=EVIDENCE, screening_criteria=CRITERIA
    )

    assert result.include is include
    assert result.probability == probability
    assert result.threshold == 0.5
    assert result.model == "gpt-6-luna"
    assert result.reasoning.startswith("Included" if include else "Excluded")


def test_a_configured_threshold_decides_and_is_reported():
    screener = EvidenceScreener(lm=decision_lm(0.83))
    screener.screen.fields["meets_criteria"] = {"threshold": 0.9}

    result = screener(evidence=EVIDENCE, screening_criteria=CRITERIA)

    assert result.include is False
    assert result.threshold == 0.9
    assert "threshold of 90%" in result.reasoning


def test_sends_one_predicate_named_after_the_decision_field():
    requests: list = []
    EvidenceScreener(lm=decision_lm(0.5, requests))(
        evidence=EVIDENCE, screening_criteria=CRITERIA
    )

    (body,) = requests
    assert body["model"] == "gpt-6-luna"
    (question,) = body["questions"]
    assert question["name"] == "meets_criteria"
    assert question["type"] == "predicate"
