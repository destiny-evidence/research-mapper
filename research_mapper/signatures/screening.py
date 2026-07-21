import dspy

from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.screening import ScreeningCriterion


class UserQueryToScreeningCriteria(dspy.Signature):
    """
    Generate a set of inclusion and exclusion criteria for evidence that could help answer a user's query.
    """

    original_query: UserQuery = dspy.InputField(
        desc="The original user query for context."
    )
    screening_criteria: list[ScreeningCriterion] = dspy.OutputField(
        desc="A list of inclusion and exclusion criteria to screen evidence for."
    )


class ScreenEvidenceUsingCriteria(dspy.Signature):
    """
    Screen a piece of evidence using provided inclusion and exclusion criteria.
    """

    evidence: Evidence = dspy.InputField(
        desc="A potential piece of evidence to screen for relevance."
    )
    screening_criteria: list[ScreeningCriterion] = dspy.InputField(
        desc="A list of inclusion and exclusion criteria to abide by."
    )
    include: bool = dspy.OutputField(
        desc="Whether the piece of evidence should be included or not."
    )
