import logging
from typing import Annotated

from destiny_sdk.search import AnnotationFilter

from research_mapper.config import get_destiny_client
from research_mapper.destiny import evidence_from_destiny_reference
from research_mapper.models.common import EvidencePage, RetrievalPageResult
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.taxonomy import COMMUNITY_ANNOTATION_LABELS, RepoCommunity

logger = logging.getLogger(__name__)


def search_references(
    query: Annotated[LuceneQuery, "The search query in Lucene syntax."],
    community: RepoCommunity,
    start_year: Annotated[int | None, "The start year for filtering results."] = None,
    end_year: Annotated[int | None, "The end year for filtering results."] = None,
    sort: Annotated[
        str | None,
        "The field to sort the results by. Prefix a field with '-' to sort in descending order. If omitted, will sort by relevance score descending.",
    ] = None,
    page: Annotated[int, "The page number of the results to retrieve."] = 1,
) -> EvidencePage:
    """Search the DESTINY evidence repository for references, scoped to a single
    repository community via its domain-inclusion annotation.
    Returns a page of matching references, plus total-match metadata."""
    logger.debug(
        "search_references(query=%s, community=%s, start_year=%s, end_year=%s, sort=%s, page=%s)",
        query.query,
        community,
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
        annotations=[
            AnnotationFilter(
                scheme="domain-inclusion",
                label=COMMUNITY_ANNOTATION_LABELS[community],
            )
        ],
        sort=sort,
        page=page,
    )

    evidence = [evidence_from_destiny_reference(ref) for ref in result.references]
    logger.debug("search_references returned %d results", len(evidence))
    return EvidencePage(
        evidence=evidence,
        total_count=result.total.count,
        is_total_lower_bound=result.total.is_lower_bound,
    )


class SearchReferencesTool:
    """
    A version of the search_references tool fixed to a single search query and
    repository community. Results are accumulated into `retrieved`, keyed by
    destiny_id, so the caller can access all fetched Evidence regardless of what the
    LLM puts in its output field.
    """

    def __init__(self, query: LuceneQuery, community: RepoCommunity) -> None:
        """
        :param query: the query to fix the tool with
        :param community: the repository community to fix the tool with
        """
        self.query = query
        self.community = community
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
    ) -> RetrievalPageResult:
        """Search the DESTINY evidence repository for references, as a page of
        structured summaries (title/abstract/year/venue) plus pagination metadata —
        enough to judge relevance and decide when to stop."""
        page_result = search_references(
            query=self.query,
            community=self.community,
            start_year=start_year,
            end_year=end_year,
            sort=sort,
            page=page,
        )
        self.retrieved.update({ev.destiny_id: ev for ev in page_result.evidence})
        return RetrievalPageResult.from_page(page_result)
