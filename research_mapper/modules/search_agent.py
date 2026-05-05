import asyncio
import logging
from itertools import chain
from typing import Annotated, Callable, Any

import dspy

from research_mapper.models import UserQuery, LuceneQuery, Evidence
from research_mapper.modules.utils import read_reasoning_stream
from research_mapper.signatures import (
    UserQueryToLuceneSearchQueries,
    GatherEvidenceFromSearchQuery,
)
from research_mapper.tools import search_references, lookup_references
from research_mapper.ui import LiveAgentPanels, TerminalUI, LiveAgentPanel

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
    def __init__(self, tui: TerminalUI | None = None):
        self.query_generator = dspy.ChainOfThought(UserQueryToLuceneSearchQueries)
        self.tui = tui

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        return asyncio.run(self.aforward(user_query))

    async def aforward(self, user_query: UserQuery) -> dspy.Prediction:
        search_queries = self._generate_search_queries(user_query)
        search_queries = self._filter_search_queries_by_user(search_queries)
        evidence = await self._retrieve_evidence(user_query, search_queries)
        logger.info("SearchAgent complete — %d evidence items returned", len(evidence))
        return dspy.Prediction(evidence=list(evidence))

    def _filter_search_queries_by_user(
        self, search_queries: list[LuceneQuery]
    ) -> list[LuceneQuery]:
        if self.tui:
            return self.tui.select_from_list(
                search_queries, title="Suggested search queries"
            )
        else:
            return search_queries

    def _generate_search_queries(self, user_query: UserQuery) -> list[LuceneQuery]:
        logger.info("Generating Lucene queries for: %s", user_query.query)
        if self.tui is not None:
            with LiveAgentPanel(user_query.query, self.tui) as panel_ui:
                search_queries = read_reasoning_stream(
                    program=self.query_generator,
                    original_query=user_query,
                    on_chunk=panel_ui.get_callback_for_buffer(user_query.query),
                ).search_queries
            self.tui.print_info("[green]✓[/green] Queries generated successfully!")
        else:
            search_queries = self.query_generator(
                original_query=user_query
            ).search_queries
        logger.debug("Generated queries: %s", search_queries)
        return search_queries

    async def _retrieve_evidence(
        self, user_query: UserQuery, search_queries: list[LuceneQuery]
    ) -> set[Evidence]:
        logger.info(
            "Starting subagent retrieval loop — %d queries to process",
            len(search_queries),
        )

        def run_retrieval_subagent(
            query: LuceneQuery, on_chunk: Callable[[str, bool], Any] | None = None
        ) -> list[Evidence]:
            _search_references = fixed_search_references_builder(query)
            subagent = dspy.ReAct(
                signature=GatherEvidenceFromSearchQuery,
                tools=[_search_references, lookup_references],
                max_iters=5,
            )
            if on_chunk is not None:
                new_evidence = read_reasoning_stream(
                    subagent,
                    on_chunk=on_chunk,
                    original_query=user_query,
                    search_query=query,
                )
            else:
                new_evidence = subagent(original_query=user_query, search_query=query)

            logger.info("Found %d new items for: %s", len(new_evidence.evidence), query)
            logger.info(
                'Agent stopped searching for %s because: "%s"',
                query,
                new_evidence.stopping_reason,
            )
            return new_evidence.evidence

        if self.tui is not None:
            with LiveAgentPanels(search_queries, self.tui) as subagent_ui:
                results = await asyncio.gather(
                    *[
                        asyncio.to_thread(
                            run_retrieval_subagent,
                            query,
                            subagent_ui.get_callback_for_buffer(query),
                        )
                        for query in search_queries
                    ]
                )
            self.tui.print_info("[green]✓[/green] Evidence retrieved successfully!")
        else:
            results = await asyncio.gather(
                *[
                    asyncio.to_thread(run_retrieval_subagent, query)
                    for query in search_queries
                ]
            )

        return set(chain.from_iterable(results))
