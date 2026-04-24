import logging
import uuid
from typing import Annotated

from destiny_sdk.identifiers import IdentifierLookup, Identifier

from .models import LuceneQuery, Evidence
from .config import get_destiny_client

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


def lookup_references(
    identifiers: Annotated[list[Identifier], "The identifiers to look up."],
) -> list[Evidence]:
    """Look up specific references by their identifiers (DOI, PubMed ID, etc.).
    Pass identifiers as strings; the SDK will auto-detect the type."""
    logger.debug("lookup_references(identifiers=%s)", identifiers)
    client = get_destiny_client()

    lookups = []
    for identifier in identifiers:
        if isinstance(identifier, uuid.UUID):
            lookup_identifier = IdentifierLookup(
                identifier=str(identifier), identifier_type=None
            )
        else:
            lookup_identifier = IdentifierLookup(
                identifier=str(identifier.identifier),
                identifier_type=identifier.identifier_type,
            )
        lookups.append(lookup_identifier)

    results = client.lookup(lookups)

    evidence = [Evidence.from_destiny_reference(ref) for ref in results]
    logger.debug("lookup_references returned %d results", len(evidence))
    return evidence
