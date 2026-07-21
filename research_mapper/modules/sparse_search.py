import logging

import dspy

from research_mapper.models import UserQuery, LuceneQuery
from research_mapper.signatures.sparse_search import (
    UserQueryToLuceneSearchQueries,
    GatherEvidenceFromSearchQuery,
)
from research_mapper.tools.sparse_search import fixed_search_references_builder

logger = logging.getLogger(__name__)


class SparseQueryGenerator(dspy.Module):
    """
    Generates a set of candidate Lucene search queries for a user's query.
    """

    def __init__(self) -> None:
        self.generate = dspy.ChainOfThought(UserQueryToLuceneSearchQueries)

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Generates Lucene search queries for a user's query.
        :param user_query: the user query to generate search queries for
        :return: a Prediction wrapping the suggested search_queries and their reasoning
        """
        logger.info("Generating Lucene queries for: %s", user_query.query)
        prediction = self.generate(original_query=user_query)
        logger.debug("Generated queries: %s", prediction.search_queries)
        return prediction


class EvidenceRetriever(dspy.Module):
    """
    Dispatches a DSPy subagent to retrieve Evidence from the DESTINY repository for a single
    Lucene search query. Intended to be driven over many search queries via `dspy.Module.batch`.
    """

    def forward(
        self, user_query: UserQuery, search_query: LuceneQuery
    ) -> dspy.Prediction:
        """
        Retrieves Evidence for a single search query.
        :param user_query: the original user query, for context
        :param search_query: the search query to retrieve evidence for
        :return: a Prediction wrapping the retrieved evidence, alongside the subagent's
            search_summary, stopping_reason, and reasoning
        """
        retrieved: dict = {}
        _search_references = fixed_search_references_builder(search_query, retrieved)
        subagent = dspy.ReAct(
            signature=GatherEvidenceFromSearchQuery,
            tools=[_search_references],
            max_iters=5,
        )
        prediction = subagent(original_query=user_query, search_query=search_query)

        logger.info("Found %d new items for: %s", len(retrieved), search_query)
        logger.debug(
            "Search summary for %s: %s", search_query, prediction.search_summary
        )
        logger.info(
            'Agent stopped searching for %s because: "%s"',
            search_query,
            prediction.stopping_reason,
        )
        return dspy.Prediction(
            evidence=list(retrieved.values()),
            search_summary=prediction.search_summary,
            stopping_reason=prediction.stopping_reason,
            reasoning=prediction.reasoning,
        )
