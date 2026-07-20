import logging
from typing import Annotated, Callable, Optional

import dspy

from research_mapper.models import UserQuery, LuceneQuery, Evidence
from research_mapper.signatures import (
    UserQueryToLuceneSearchQueries,
    GatherEvidenceFromSearchQuery,
)
from research_mapper.tools import search_references

logger = logging.getLogger(__name__)


# easy partial application approaches like functools' partial function don't
# work well/cleanly here because DSPy wraps functions that are meant to be
# used as tools in their dspy.Tool object that relies on function metadata
# (i.e. __name__, __doc__, etc) to let the LLM know how to call the function
def _fixed_search_references_builder(
    query: LuceneQuery,
    retrieved: dict,
) -> Callable[[Optional[int], Optional[int], Optional[str], int], list[Evidence]]:
    """
    Creates a version of the search_references tool with a fixed search query.
    Results are accumulated into retrieved keyed by destiny_id so the caller
    can access all fetched Evidence regardless of what the LLM puts in its output field.
    :param query: the query to fix the tool with
    :param retrieved: shared dict to accumulate fetched Evidence objects into
    :return: a fixed version of the search_references tool
    """

    def _search_references(
        start_year: Annotated[
            int | None, "The start year for filtering results."
        ] = None,
        end_year: Annotated[int | None, "The end year for filtering results."] = None,
        sort: Annotated[
            str | None,
            "The field to sort the results by. Prefix a field with '-' to sort in descending order. If omitted, will sort by relevance score descending.",
        ] = None,
        page: Annotated[int, "The page number of the results to retrieve."] = 1,
    ) -> list[Evidence]:
        """
        Query-fixed version of the DESTINY search_references tool.
        :return: list of references retrieved from DESTINY as evidence objects
        """
        results = search_references(
            query=query, start_year=start_year, end_year=end_year, sort=sort, page=page
        )
        retrieved.update({ev.destiny_id: ev for ev in results})
        return results

    return _search_references


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
        _search_references = _fixed_search_references_builder(search_query, retrieved)
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
