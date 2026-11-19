"""ChainOfThought's reasoning must leave our modules as a plain str.

Since DSPy 3.5 it is a dspy.Reasoning, which artifacts' `reasoning: str` fields and
JSON columns both reject.
"""

import json
from unittest.mock import MagicMock

import dspy

from research_mapper.models.common import UserQuery
from research_mapper.models.screening import ScreeningCriterion, ScreeningCriterionType
from research_mapper.modules.common import plain_reasoning
from research_mapper.modules.screening import CriteriaGenerator
from research_mapper.workflows.evidence_map import artifacts


def test_a_reasoning_object_becomes_its_text():
    prediction = plain_reasoning(
        dspy.Prediction(reasoning=dspy.Reasoning(content="because"))
    )

    assert prediction.reasoning == "because"
    assert isinstance(prediction.reasoning, str)


def test_the_original_prediction_keeps_its_reasoning_object():
    """The original is what DSPy recorded in its optimiser trace, so few-shot
    examples bootstrapped from it must keep the dspy.Reasoning it produced."""
    original = dspy.Prediction.from_completions(
        [
            {"reasoning": dspy.Reasoning(content="first"), "answer": "a"},
            {"reasoning": dspy.Reasoning(content="second"), "answer": "b"},
        ]
    )

    plain = plain_reasoning(original)

    assert plain.reasoning == "first"
    assert isinstance(original.reasoning, dspy.Reasoning)
    assert len(plain.completions) == 2, "other completions survive the copy"


def test_a_traced_predictors_record_is_not_rewritten():
    generator = CriteriaGenerator()
    traced = dspy.Prediction(
        reasoning=dspy.Reasoning(content="why"), screening_criteria=[]
    )
    generator.generate = MagicMock(return_value=traced)

    generator(user_query=UserQuery(query="q"))

    assert isinstance(traced.reasoning, dspy.Reasoning)


def test_no_reasoning_summary_from_a_native_reasoning_model_becomes_empty_text():
    """DSPy leaves reasoning None when the provider returns no reasoning summary,
    and artifacts' `reasoning: str` fields reject None."""
    generator = CriteriaGenerator()
    generator.generate = MagicMock(
        return_value=dspy.Prediction(reasoning=None, screening_criteria=[])
    )

    prediction = generator(user_query=UserQuery(query="q"))

    assert prediction.reasoning == ""
    artifacts.ScreeningCriteria(criteria=[], reasoning=prediction.reasoning)


def test_predictions_without_reasoning_are_left_alone():
    assert "reasoning" not in plain_reasoning(dspy.Prediction(answer="x"))
    assert plain_reasoning(dspy.Prediction(reasoning="already text")).reasoning == (
        "already text"
    )


def test_a_chain_of_thought_module_returns_reasoning_an_artifact_accepts():
    generator = CriteriaGenerator()
    generator.generate = MagicMock(
        return_value=dspy.Prediction(
            reasoning=dspy.Reasoning(content="Heat and health are both needed."),
            screening_criteria=[
                ScreeningCriterion(
                    criterion_type=ScreeningCriterionType.INCLUSION,
                    description="about heat",
                )
            ],
        )
    )

    prediction = generator(user_query=UserQuery(query="heat and health"))

    stored = artifacts.ScreeningCriteria(
        criteria=prediction.screening_criteria, reasoning=prediction.reasoning
    )
    assert stored.reasoning == "Heat and health are both needed."
    json.dumps(stored.model_dump(mode="json"))
