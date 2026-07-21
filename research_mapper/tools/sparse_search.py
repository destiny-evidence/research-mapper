import inspect
import logging
from typing import Annotated, Callable

from research_mapper.config import get_destiny_client
from research_mapper.models import Evidence, LuceneQuery

logger = logging.getLogger(__name__)


def search_references(
    query: Annotated[LuceneQuery, "The search query in Lucene syntax."],
    start_year: Annotated[int | None, "The start year for filtering results."] = None,
    end_year: Annotated[int | None, "The end year for filtering results."] = None,
    sort: Annotated[
        str | None,
        "The field to sort the results by. Prefix a field with '-' to sort in descending order. If omitted, will sort by relevance score descending.",
    ] = None,
    page: Annotated[int, "The page number of the results to retrieve."] = 1,
) -> list[Evidence]:
    """Search the DESTINY evidence repository for references.
    Returns a page of matching references with metadata."""
    logger.debug(
        "search_references(query=%s, start_year=%s, end_year=%s, sort=%s, page=%s)",
        query.query,
        start_year,
        end_year,
        sort,
        page,
    )
    client = get_destiny_client()

    result = client.search(
        query=query.query,
        start_year=start_year,
        end_year=end_year,
        annotations=None,
        sort=sort,
        page=page,
    )

    evidence = [Evidence.from_destiny_reference(ref) for ref in result.references]
    logger.debug("search_references returned %d results", len(evidence))
    return evidence


def fixed_search_references_builder(
    query: LuceneQuery, retrieved: dict
) -> Callable[..., list[Evidence]]:
    """
    Creates a version of the search_references tool with a fixed search query. Results are
    accumulated into retrieved keyed by destiny_id so the caller can access all fetched Evidence
    regardless of what the LLM puts in its output field. Its exposed signature and argument
    annotations are derived from search_references' own (minus the now-fixed 'query' parameter),
    so they can't drift out of sync with it.
    :param query: the query to fix the tool with
    :param retrieved: shared dict to accumulate fetched Evidence objects into
    :return: a fixed version of the search_references tool
    """

    def _search_references(**kwargs) -> list[Evidence]:
        """Query-fixed version of the DESTINY search_references tool."""
        results = search_references(query=query, **kwargs)
        retrieved.update({ev.destiny_id: ev for ev in results})
        return results

    original_signature = inspect.signature(search_references)
    _search_references.__signature__ = original_signature.replace(
        parameters=[
            param
            for name, param in original_signature.parameters.items()
            if name != "query"
        ]
    )
    _search_references.__annotations__ = {
        name: annotation
        for name, annotation in search_references.__annotations__.items()
        if name != "query"
    }
    return _search_references
