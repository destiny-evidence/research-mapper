"""Retrieves DESTINY evidence directly via resolved taxonomy concept filters."""

import logging

from destiny_sdk.search import AnnotationFilter

from research_mapper.config import get_destiny_client
from research_mapper.destiny import evidence_from_destiny_reference
from research_mapper.models.common import Evidence
from research_mapper.taxonomy import COMMUNITY_ANNOTATION_LABELS, RepoCommunity

logger = logging.getLogger(__name__)


def retrieve_evidence_by_concepts(
    community: RepoCommunity, concepts: list[str | list[str]]
) -> list[Evidence]:
    """
    Retrieves DESTINY evidence matching the given resolved concept filters, scoped to a
    single repository community via its domain-inclusion annotation. No free-text query
    constraint is applied.
    :param community: the repository community to scope the search to
    :param concepts: resolved concept IRI filters, AND'd across entries and OR'd within
        an entry, as produced by IndexedVocab.resolve
    :return: the matching evidence
    """
    label = COMMUNITY_ANNOTATION_LABELS[community]
    logger.debug(
        "retrieve_evidence_by_concepts(community=%s, concepts=%s)", community, concepts
    )
    client = get_destiny_client()

    result = client.search(
        query="*",
        concepts=concepts,
        annotations=[AnnotationFilter(scheme="domain-inclusion", label=label)],
        # A wildcard query with concept/annotation filtering is a heavier server-side
        # query than a narrow Lucene search; the client's 10s default isn't enough.
        timeout=60,
    )

    evidence = [evidence_from_destiny_reference(ref) for ref in result.references]
    logger.debug("retrieve_evidence_by_concepts returned %d results", len(evidence))
    return evidence
