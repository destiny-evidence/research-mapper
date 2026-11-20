"""Every ChainOfThought module asks the model to write its reasoning out.

Since DSPy 3.5, a default ChainOfThought on a natively reasoning model drops the
written field and reads reasoning from the provider's summary, which can be missing.
We store and show this reasoning, so each module opts into a written `str` field
(DSPy's documented choice for a human-auditable plan). Native reasoning effort is set
once on the LM instead (MAPPER_LLM_REASONING_EFFORT).
"""

from unittest.mock import MagicMock, patch

import dspy
import pytest

from research_mapper.models.common import UserQuery
from research_mapper.modules.mapping import DimensionGenerator, SubtopicGenerator
from research_mapper.modules.screening import CriteriaGenerator
from research_mapper.modules.sparse_search import SparseQueryGenerator
from research_mapper.modules.taxonomy_mapping import TaxonomySchemeDimensionGenerator


@pytest.mark.parametrize(
    "module",
    [CriteriaGenerator, DimensionGenerator, SubtopicGenerator, SparseQueryGenerator],
)
def test_reasoning_is_a_written_text_field(module):
    reasoning = module().generate.predict.signature.output_fields["reasoning"]

    assert reasoning.annotation is str


def test_the_taxonomy_scheme_selector_asks_for_written_reasoning():
    chain_of_thought = MagicMock()
    # The same scheme three times stops forward() before it builds any dimensions.
    chain_of_thought.return_value.return_value = dspy.Prediction(
        scheme1="A", scheme2="A", scheme3="A", reasoning="why"
    )

    with (
        patch(
            "research_mapper.modules.taxonomy_mapping.dspy.ChainOfThought",
            chain_of_thought,
        ),
        pytest.raises(RuntimeError, match="more than once"),
    ):
        TaxonomySchemeDimensionGenerator()(
            user_query=UserQuery(query="q"),
            indexed_vocab=MagicMock(),
            available_schemes=["A", "B", "C"],
        )

    assert chain_of_thought.call_args.kwargs["rationale_field_type"] is str
