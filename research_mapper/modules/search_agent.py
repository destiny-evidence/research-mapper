import asyncio
import logging
from itertools import chain
from typing import Annotated, Callable, Any, Optional

import dspy

from research_mapper.models import UserQuery, LuceneQuery, Evidence
from research_mapper.modules.utils import (
    MAX_CONCURRENCY,
    read_reasoning_stream,
    run_with_semaphore,
)
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
def fixed_search_references_builder(
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


def lookup_references_builder(retrieved: dict) -> Callable:
    """
    Creates a version of the lookup_references tool that accumulates results into retrieved.
    :param retrieved: shared dict to accumulate fetched Evidence objects into
    :return: a tracking version of the lookup_references tool
    """

    def _lookup_references(
        identifiers: Annotated[list, "The identifiers to look up."],
    ) -> list[Evidence]:
        """Look up specific references by their identifiers (DOI, PubMed ID, etc.).
        Pass identifiers as strings; the SDK will auto-detect the type."""
        results = lookup_references(identifiers)
        retrieved.update({ev.destiny_id: ev for ev in results})
        return results

    return _lookup_references


class SearchAgent(dspy.Module):
    """
    A DSPy program/module to semi-automatically retrieve evidence from the DESTINY repository
    given a query.
    """

    def __init__(self, tui: TerminalUI | None = None) -> None:
        self.query_generator = dspy.ChainOfThought(UserQueryToLuceneSearchQueries)
        self.tui = tui

    def forward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Implements DSPy Module's forward method by wrapping the aforward one.
        :param user_query: the user query evidence needs to be searched for
        :return: a DSPy Prediction wrapping a collection of retrieved Evidence objects
        """
        return asyncio.run(self.aforward(user_query))

    async def aforward(self, user_query: UserQuery) -> dspy.Prediction:
        """
        Generates a set of Lucene search queries, validates them by the user, and dispatches subagents
        to retrieve potential evidence for each search query.

        :param user_query: the user query evidence needs to be searched for
        :return: a DSPy Prediction wrapping a collection of retrieved Evidence objects
        """
        search_queries = self._generate_search_queries(user_query)
        search_queries = self._filter_search_queries_by_user(search_queries)
        evidence = await self._retrieve_evidence(user_query, search_queries)
        logger.info("SearchAgent complete — %d evidence items returned", len(evidence))
        return dspy.Prediction(evidence=list(evidence))

    def _filter_search_queries_by_user(
        self, search_queries: list[LuceneQuery]
    ) -> list[LuceneQuery]:
        """
        Prompts user to filter generated search queries via a UI. Keeps them all if not.
        :param search_queries: the search queries to be filtered/validated
        :return: the filtered search queries
        """
        if self.tui:
            return self.tui.select_from_list(
                search_queries, title="Suggested search queries"
            )
        else:
            return search_queries

    def _generate_search_queries(self, user_query: UserQuery) -> list[LuceneQuery]:
        """
        Generates a set of candidate Lucene queries to search the DESTINY respository with.
        :param user_query: the user's query to generate search queries for
        :return: a collection of Lucene search queries
        """
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
    ) -> list[Evidence]:
        """
        Dispatches DSPy subagents for each search query to retrieve references from the DESTINY repository.
        :param user_query: the original user's query for context
        :param search_queries: the search queries to be applied to the DESTINY repository
        :return: a set of unique Evidence objects
        """
        logger.info(
            "Starting subagent retrieval loop — %d queries to process",
            len(search_queries),
        )

        def run_retrieval_subagent(
            query: LuceneQuery, on_chunk: Callable[[str, bool], Any] | None = None
        ) -> list[Evidence]:
            """
            Builds and runs an Evidence retrieval subagent for a specific search query.
            :param query: the search query to retrieve evidence for
            :param on_chunk: the callback to be used if and when chunks are streamed from the subagent's underlying LLM
            :return: a list of retrieved Evidence objects
            """
            retrieved: dict = {}
            _search_references = fixed_search_references_builder(query, retrieved)
            _lookup_references = lookup_references_builder(retrieved)
            subagent = dspy.ReAct(
                signature=GatherEvidenceFromSearchQuery,
                tools=[_search_references, _lookup_references],
                max_iters=5,
            )
            # equivalent to checking if we're in "UI-mode" i.e. we have a UI
            if on_chunk is not None:
                new_evidence = read_reasoning_stream(
                    subagent,
                    on_chunk=on_chunk,
                    original_query=user_query,
                    search_query=query,
                )
            else:
                new_evidence = subagent(original_query=user_query, search_query=query)

            logger.info("Found %d new items for: %s", len(retrieved), query)
            logger.debug(
                "Search summary for %s: %s", query, new_evidence.search_summary
            )
            logger.info(
                'Agent stopped searching for %s because: "%s"',
                query,
                new_evidence.stopping_reason,
            )
            return list(retrieved.values())

        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        if self.tui is not None:
            with LiveAgentPanels(search_queries, self.tui) as subagent_ui:
                results = await asyncio.gather(
                    *[
                        run_with_semaphore(
                            run_retrieval_subagent,
                            semaphore,
                            query=query,
                            on_chunk=subagent_ui.get_callback_for_buffer(query),
                        )
                        for query in search_queries
                    ]
                )
            self.tui.print_info("[green]✓[/green] Evidence retrieved successfully!")
        else:
            results = await asyncio.gather(
                *[
                    run_with_semaphore(run_retrieval_subagent, semaphore, query=query)
                    for query in search_queries
                ]
            )

        return list(set(chain.from_iterable(results)))
