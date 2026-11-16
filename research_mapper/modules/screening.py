import dspy

from research_mapper.config import get_decision_model
from research_mapper.models.common import Evidence, UserQuery
from research_mapper.models.screening import ScreeningCriterion
from research_mapper.signatures.screening import (
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

    def __init__(self, lm: dspy.LM | None = None) -> None:
        self.screen = dspy.Predict(ScreenEvidenceUsingCriteria)
        if lm is not None:
            self.screen.set_lm(lm)

    def forward(
        self, evidence: Evidence, screening_criteria: list[ScreeningCriterion]
    ) -> dspy.Prediction:
        """
        Screens a piece of evidence against a set of screening criteria.
        :param evidence: the piece of evidence to screen
        :param screening_criteria: the screening criteria to screen it against
        :return: a Prediction of plain values: include (bool), probability (P(meets
            criteria)), the threshold it was judged against, and reasoning
        """
        if self.screen.lm is None:
            self.screen.set_lm(get_decision_model())

        pred = self.screen(evidence=evidence, screening_criteria=screening_criteria)
        decision = pred.meets_criteria  # a Noul; it stays inside this module
        criteria = decision.criteria()
        # DSPy applies 0.5 when no threshold has been configured.
        threshold = self.screen.fields.get("meets_criteria", {}).get("threshold", 0.5)
        include = decision.value
        reasoning = (
            f"{'Included' if include else 'Excluded'}: "
            f"{criteria['true' if include else 'false']} "
            f"Probability of meeting the criteria was {decision.probability:.0%} "
            f"({decision.probability:.4f}) against a threshold of {threshold:.0%} "
            f"(confidence {decision.confidence:.0%}), per {self.screen.lm.model}."
        )
        return dspy.Prediction(
            include=include,
            probability=decision.probability,
            threshold=threshold,
            model=self.screen.lm.model,
            reasoning=reasoning,
        )
