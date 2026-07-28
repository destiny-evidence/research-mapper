from unittest.mock import MagicMock

from research_mapper.models.common import UserQuery
from research_mapper.modules.taxonomy_search import TaxonomyConceptFilterGenerator


def test_forward_resets_unsatisfiable_reason_between_calls():
    """
    self.agent/self._unsatisfiability_tool are built once in __init__ and reused across
    calls (that's what makes run_with_status's live streaming work here); a reason left
    over from a previous call must not leak into the next one.
    """
    generator = TaxonomyConceptFilterGenerator()

    mock_prediction = MagicMock()
    mock_prediction.filter_groups = []

    def agent_marks_unsatisfiable(**kwargs):
        # Simulates the ReAct loop internally calling mark_unsatisfiable mid-run.
        generator._unsatisfiability_tool.mark_unsatisfiable("no matching concept")
        return mock_prediction

    generator.agent = MagicMock(side_effect=agent_marks_unsatisfiable)
    first = generator.forward(UserQuery(query="q1"), taxonomy_concepts=[])
    assert first.unsatisfiable_reason == "no matching concept"

    generator.agent = MagicMock(return_value=mock_prediction)
    second = generator.forward(UserQuery(query="q2"), taxonomy_concepts=[])
    assert second.unsatisfiable_reason is None
