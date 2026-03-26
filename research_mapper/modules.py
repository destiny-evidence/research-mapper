import logging

import dspy

from .models import UserQuery
from .signatures import UserQueryToLuceneSearchQueries, GatherEvidenceFromSearchQuery
from .human_in_loop import validate_search_queries
from .tools import search_references, lookup_references
from .ui import Spinner

logger = logging.getLogger(__name__)


class SearchAgent(dspy.Module):
    def __init__(self):
        self.query_generator = dspy.ChainOfThought(UserQueryToLuceneSearchQueries)
        self.agent = dspy.ReAct(
            signature=GatherEvidenceFromSearchQuery,
            tools=[search_references, lookup_references],
            max_iters=5,
        )

    def forward(self, user_query: UserQuery):
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
        evidence = set()
        for query in search_queries:
            logger.debug("Running ReAct agent for query: %s", query)
            with Spinner("Searching"):
                new_evidence = self.agent(
                    original_query=user_query, search_query=query
                ).evidence
                evidence.update(new_evidence)
            logger.info("Found %d new items for: %s", len(new_evidence), query)

        logger.info("SearchAgent complete — %d evidence items returned", len(evidence))
        return dspy.Prediction(evidence=list(evidence))
