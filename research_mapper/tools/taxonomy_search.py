import logging
from typing import Annotated

from destiny_sdk.search import AnnotationFilter
from rdflib import SKOS, Graph, URIRef

from research_mapper.config import get_destiny_client
from research_mapper.destiny import evidence_from_destiny_reference
from research_mapper.models.taxonomy_search import (
    ClarificationOptions,
    ConceptSearchPage,
    IndexedVocab,
)
from research_mapper.taxonomy import COMMUNITY_ANNOTATION_LABELS, RepoCommunity

logger = logging.getLogger(__name__)


class TaxonomyBrowsingTools:
    """
    Lets the concept-filter-generation agent explore a taxonomy on demand —
    list its schemes, browse or search within one, and (for the minority of
    schemes that have it) walk skos:broader/narrower — rather than the whole
    vocabulary being stuffed into context upfront. Bound to one community's
    already-built IndexedVocab (for scheme/label/detail lookups — cheap, no
    graph queries needed) and its rdflib Graph (needed only for broader/
    narrower, since IndexedVocab doesn't carry hierarchy).
    """

    def __init__(self, graph: Graph, indexed: IndexedVocab) -> None:
        self._graph = graph
        self._by_ref = {concept.local_ref: concept for concept in indexed.concepts}
        self._local_ref_to_iri = indexed.local_ref_to_iri
        self._iri_to_ref = {iri: ref for ref, iri in indexed.local_ref_to_iri.items()}

    def list_schemes(self) -> list[str]:
        """List every scheme (topic/category) this taxonomy is organised into."""
        return sorted({concept.scheme for concept in self._by_ref.values()})

    def list_concepts_in_scheme(self, scheme: str) -> list[str]:
        """List every concept's local_ref and label within one scheme, as returned
        by list_schemes."""
        return [
            f"{concept.local_ref}: {concept.label}"
            for concept in self._by_ref.values()
            if concept.scheme == scheme
        ]

    def search_concepts(self, query: str) -> list[str]:
        """Search concept labels and alternate labels (case-insensitive substring
        match) across every scheme."""
        needle = query.lower()
        return [
            f"{concept.local_ref}: {concept.label} ({concept.scheme})"
            for concept in self._by_ref.values()
            if needle in concept.label.lower()
            or any(needle in alt.lower() for alt in concept.alt_labels)
        ]

    def get_concept_detail(self, local_ref: str) -> str:
        """Get a concept's full label, alternate labels, and definition/scope note,
        given its local_ref."""
        concept = self._by_ref.get(local_ref)
        if concept is None:
            return f"No such concept: {local_ref}"
        parts = [f"label: {concept.label}", f"scheme: {concept.scheme}"]
        if concept.alt_labels:
            parts.append(f"alt labels: {', '.join(concept.alt_labels)}")
        if concept.detail:
            parts.append(f"detail: {concept.detail}")
        return "; ".join(parts)

    def get_broader(self, local_ref: str) -> list[str]:
        """Get the more general concept(s) a concept sits under, if any — most
        concepts have none; only a handful of schemes are hierarchical."""
        return self._related(local_ref, SKOS.broader)

    def get_narrower(self, local_ref: str) -> list[str]:
        """Get the more specific concept(s) under a concept, if any — most
        concepts have none; only a handful of schemes are hierarchical."""
        return self._related(local_ref, SKOS.narrower)

    def _related(self, local_ref: str, predicate: URIRef) -> list[str]:
        iri = self._local_ref_to_iri.get(local_ref)
        if iri is None:
            return [f"No such concept: {local_ref}"]
        related_refs = [
            self._iri_to_ref[str(related_iri)]
            for related_iri in self._graph.objects(URIRef(iri), predicate)
            if str(related_iri) in self._iri_to_ref
        ]
        return [f"{ref}: {self._by_ref[ref].label}" for ref in related_refs]


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
