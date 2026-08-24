import logging
from typing import Annotated

from destiny_sdk.search import AnnotationFilter

from research_mapper.config import get_destiny_client
from research_mapper.destiny import evidence_from_destiny_reference
from research_mapper.models.taxonomy_search import (
    ClarificationOptions,
    ConceptSearchPage,
)
from research_mapper.taxonomy import COMMUNITY_ANNOTATION_LABELS, RepoCommunity

logger = logging.getLogger(__name__)


def ask_for_clarification(request: ClarificationOptions) -> list[str]:
    """Ask the user a clarifying question — including to disambiguate between
    conflicting interpretations — giving them a fixed set of concrete options to
    choose one or more from. An "I'm not sure" option is always added automatically."""
    # This must never actually execute: a ResumableReAct caller sees the proposed
    # Step (and its `request`) before resume() would call this, does its own
    # prompting, and supplies the answer via Step.with_observation() — see
    # modules/taxonomy_search.py. This only exists to give the agent a name,
    # docstring, and argument schema to reason about and call.
    msg = "ask_for_clarification must never execute — the caller always supplies the answer"
    raise AssertionError(msg)


def mark_unsatisfiable(reason: str) -> str:
    """Call this if the user's clarified intent genuinely cannot be expressed using
    the available taxonomy concepts — e.g. no concept exists for a required part of
    the query, even after asking clarifying questions. Provide a brief reason."""
    # `reason` is already visible to the caller via the proposed Step's tool_args,
    # before this ever runs — nothing needs to be captured or remembered here.
    return "Noted. You may now finish."


def retrieve_evidence_by_concepts(
    community: RepoCommunity,
    concepts: list[str | list[str]],
    page: Annotated[int, "The page number of results to retrieve."] = 1,
) -> ConceptSearchPage:
    """
    Retrieves a page of DESTINY evidence matching the given resolved concept filters,
    scoped to a single repository community via its domain-inclusion annotation. No
    free-text query constraint is applied.
    :param community: the repository community to scope the search to
    :param concepts: resolved concept IRI filters, AND'd across entries and OR'd within
        an entry, as produced by IndexedVocab.resolve
    :param page: the page number of results to retrieve
    :return: the matching evidence for that page, plus total-match metadata
    """
    label = COMMUNITY_ANNOTATION_LABELS[community]
    logger.debug(
        "retrieve_evidence_by_concepts(community=%s, concepts=%s, page=%d)",
        community,
        concepts,
        page,
    )
    client = get_destiny_client()

    result = client.search(
        query="*",
        concepts=concepts,
        annotations=[AnnotationFilter(scheme="domain-inclusion", label=label)],
        page=page,
        # A wildcard query with concept/annotation filtering is a heavier server-side
        # query than a narrow Lucene search; the client's 10s default isn't enough.
        timeout=60,
    )

    evidence = [evidence_from_destiny_reference(ref) for ref in result.references]
    logger.debug("retrieve_evidence_by_concepts returned %d results", len(evidence))
    return ConceptSearchPage(
        evidence=evidence,
        total_count=result.total.count,
        is_total_lower_bound=result.total.is_lower_bound,
    )


class RetrieveEvidenceByConceptsTool:
    """
    A version of retrieve_evidence_by_concepts fixed to a single community and concept
    filter set. Results are accumulated into `retrieved`, keyed by destiny_id, so the
    caller can access all fetched Evidence regardless of what the LLM puts in its output
    field.
    """

    def __init__(
        self, community: RepoCommunity, concepts: list[str | list[str]]
    ) -> None:
        """
        :param community: the repository community to fix the tool with
        :param concepts: the resolved concept IRI filters to fix the tool with
        """
        self.community = community
        self.concepts = concepts
        self.retrieved: dict = {}

    def retrieve_evidence(
        self, page: Annotated[int, "The page number of results to retrieve."] = 1
    ) -> str:
        """Retrieve DESTINY evidence matching the fixed concept filters. Reports how many
        results were found on this page and in total, to help decide when to stop."""
        page_result = retrieve_evidence_by_concepts(self.community, self.concepts, page)
        self.retrieved.update({ev.destiny_id: ev for ev in page_result.evidence})
        bound = "+" if page_result.is_total_lower_bound else ""
        return (
            f"Page {page}: {len(page_result.evidence)} result(s) on this page "
            f"(total matching: {page_result.total_count}{bound})"
        )
