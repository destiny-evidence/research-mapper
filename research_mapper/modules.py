import asyncio
import logging
from typing import Annotated

import dspy

from .models import UserQuery, LuceneQuery, Evidence
from .signatures import UserQueryToLuceneSearchQueries, GatherEvidenceFromSearchQuery
from .human_in_loop import validate_search_queries
from .tools import search_references, lookup_references
from .ui import Spinner

logger = logging.getLogger(__name__)


# easy partial application approaches like functools' partial function don't
# work well/cleanly here because DSPy wraps functions that are meant to be
# used as tools in their dspy.Tool object that relies on function metadata
# (i.e. __name__, __doc__, etc) to let the LLM know how to call the function
def fixed_search_references_builder(query: LuceneQuery):
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
    ):
        """Search the DESTINY evidence repository for references.
        Returns a page of matching references with metadata."""
        return search_references(
            query=query, start_year=start_year, end_year=end_year, sort=sort, page=page
        )

    return _search_references


class SearchAgent(dspy.Module):
    def __init__(self):
        self.query_generator = dspy.ChainOfThought(UserQueryToLuceneSearchQueries)

    def forward(self, user_query: UserQuery):
        return asyncio.run(self.aforward(user_query))

    async def aforward(self, user_query: UserQuery):
        logger.info("Generating Lucene queries for: %s", user_query.query)
        search_queries = self.query_generator(original_query=user_query).search_queries
        logger.debug("Generated queries: %s", search_queries)

        while True:
            try:
                search_queries = validate_search_queries(search_queries)
                break
            except ValueError as e:
                print(f"Invalid input: {e}. Try again.")

        logger.info(
            "Starting agentic search loop — %d queries to process", len(search_queries)
        )

        async def run_retrieval_subagent(query: LuceneQuery) -> list[Evidence]:
            _search_references = fixed_search_references_builder(query)
            subagent = dspy.ReAct(
                signature=GatherEvidenceFromSearchQuery,
                tools=[_search_references, lookup_references],
                max_iters=5,
            )
            new_evidence = await asyncio.to_thread(
                subagent, original_query=user_query, search_query=query
            )
            logger.info("Found %d new items for: %s", len(new_evidence.evidence), query)
            logger.info(
                'Agent stopped searching for %s because: "%s"',
                query,
                new_evidence.stopping_reason,
            )
            return new_evidence.evidence

        with Spinner("Searching"):
            results = await asyncio.gather(
                *[run_retrieval_subagent(query) for query in search_queries]
            )

        evidence = set()
        for result in results:
            evidence.update(result)

        logger.info("SearchAgent complete — %d evidence items returned", len(evidence))
        return dspy.Prediction(evidence=list(evidence))
