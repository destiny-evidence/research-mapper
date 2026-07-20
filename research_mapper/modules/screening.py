import dspy

from research_mapper.models import Evidence, ScreeningCriterion, UserQuery
from research_mapper.signatures import (
    ScreenEvidenceUsingCriteria,
    UserQueryToScreeningCriteria,
)


class CriteriaGenerator(dspy.Module):
    """
    Generates a set of inclusion and exclusion criteria to screen evidence for relevance to a
    user's query.
    """

    def __init__(self) -> None:
        self.generate = dspy.ChainOfThought(UserQueryToScreeningCriteria)

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Generates screening criteria for a user's query.
        :param user_query: the user's original query to generate screening criteria for
        :return: a Prediction wrapping the suggested screening_criteria and their reasoning
        """
        return self.generate(original_query=user_query)


class EvidenceScreener(dspy.Module):
    """
    Screens a single piece of evidence for relevance against a set of screening criteria. Intended
    to be driven over many pieces of evidence via `dspy.Module.batch`.
    """

    def __init__(self) -> None:
        self.screen = dspy.ChainOfThought(ScreenEvidenceUsingCriteria)

    def forward(
        self, evidence: Evidence, screening_criteria: list[ScreeningCriterion]
    ) -> dspy.Prediction:
        """
        Screens a piece of evidence against a set of screening criteria.
        :param evidence: the piece of evidence to screen
        :param screening_criteria: the screening criteria to screen it against
        :return: a Prediction wrapping whether to include the evidence and its reasoning
        """
        return self.screen(evidence=evidence, screening_criteria=screening_criteria)
