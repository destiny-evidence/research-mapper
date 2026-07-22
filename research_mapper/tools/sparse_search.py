import logging
from typing import Annotated

from research_mapper.config import get_destiny_client
from research_mapper.destiny import evidence_from_destiny_reference
from research_mapper.models.common import Evidence
from research_mapper.models.sparse_search import LuceneQuery

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

    evidence = [evidence_from_destiny_reference(ref) for ref in result.references]
    logger.debug("search_references returned %d results", len(evidence))
    return evidence


class SearchReferencesTool:
    """
    A version of the search_references tool fixed to a single search query. Results are
    accumulated into `retrieved`, keyed by destiny_id, so the caller can access all fetched
    Evidence regardless of what the LLM puts in its output field.
    """

    def __init__(self, query: LuceneQuery) -> None:
        """
        :param query: the query to fix the tool with
        """
        self.query = query
        self.retrieved: dict = {}

    def search_references(
        self,
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
        """Search the DESTINY evidence repository for references.
        Returns a page of matching references with metadata."""
        results = search_references(
            query=self.query,
            start_year=start_year,
            end_year=end_year,
            sort=sort,
            page=page,
        )
        self.retrieved.update({ev.destiny_id: ev for ev in results})
        return results
