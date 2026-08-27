"""Fetches and indexes taxonomy/vocabulary JSON-LD for concept-filter generation."""

import json
import logging
from enum import StrEnum, auto
from functools import lru_cache

import httpx
from rdflib import RDF, SKOS, Graph, URIRef
from rdflib.namespace import DCTERMS

from research_mapper.models.taxonomy_search import Concept, IndexedVocab

logger = logging.getLogger(__name__)


class RepoCommunity(StrEnum):
    HPV = auto()
    ESEA = auto()


_VOCAB_URLS: dict[RepoCommunity, str] = {
    RepoCommunity.HPV: "https://vocab.evidence-repository.org/published/019d3e6a-04d6-76e9-9f7a-b8b26c1e0976/2.3/vocabulary.jsonld",
    RepoCommunity.ESEA: "https://vocab.evidence-repository.org/published/019d9463-2780-7243-b4de-e547386f2a90/1.1/vocabulary.jsonld",
}

# The label a community is tagged with under DESTINY's "domain-inclusion" annotation
# scheme. Not always the same as the RepoCommunity name — ESEA's is "jacobs-education".
COMMUNITY_ANNOTATION_LABELS: dict[RepoCommunity, str] = {
    RepoCommunity.HPV: "hpv",
    RepoCommunity.ESEA: "jacobs-education",
}


class TaxonomyFetchError(Exception):
    """Raised when a taxonomy/vocabulary JSON-LD document can't be fetched or parsed."""


@lru_cache
def get_taxonomy(community: RepoCommunity) -> dict:
    """
    Fetches the raw vocabulary JSON-LD document for a repository community. Cached —
    called at both concept-filter-generation and (taxonomy-scheme) mapping stages
    within a single run, and there's no reason to re-fetch the same community's
    vocabulary twice.
    :param community: the repository community to fetch the taxonomy for
    :return: the raw, parsed vocabulary JSON-LD document
    """
    url = _VOCAB_URLS[community]
    logger.debug("Fetching taxonomy for %s from %s", community, url)
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch taxonomy from %s: %s", url, exc)
        raise TaxonomyFetchError(f"Could not fetch taxonomy from {url}") from exc

    try:
        return response.json()
    except ValueError as exc:
        logger.error("Non-JSON response fetching taxonomy from %s", url)
        raise TaxonomyFetchError(f"Invalid JSON from {url}") from exc


@lru_cache
def get_graph(community: RepoCommunity) -> Graph:
    """
    Fetches (via get_taxonomy) and parses a community's vocabulary into an rdflib Graph
    — the single loader both `build_concept_index` (a flat structure for non-agent
    consumers: direct evidence-to-scheme mapping, subtopic pulling) and the taxonomy
    browsing tools (organic, on-demand exploration for the concept-filter-generation
    agent) are built from. Cached for the same reason get_taxonomy is.
    :param community: the repository community to fetch/parse the taxonomy for
    :return: the vocabulary as an rdflib Graph
    """
    vocab = get_taxonomy(community)
    graph = Graph()
    graph.parse(data=json.dumps(vocab), format="json-ld")
    return graph


def _first_literal(graph: Graph, subject: URIRef, *predicates: URIRef) -> str | None:
    """
    Reads the first present literal value off a subject, trying each predicate in
    order — e.g. preferring skos:definition, falling back to skos:scopeNote.
    :param graph: the graph to read from
    :param subject: the subject node to read predicates off
    :param predicates: candidate predicates to try, in priority order
    :return: the first literal value found, or None if none of the predicates are set
    """
    for predicate in predicates:
        value = graph.value(subject, predicate)
        if value is not None:
            return str(value)
    return None


@lru_cache
def build_concept_index(graph: Graph) -> IndexedVocab:
    """
    Builds a flat, internal concept index from a taxonomy's rdflib Graph — the
    representation non-agent consumers need (a direct IRI/local_ref-to-Concept lookup),
    as opposed to the taxonomy browsing tools, which query the same graph on demand.

    The returned Concepts never carry their IRI directly;
    `IndexedVocab.local_ref_to_iri`/`resolve` is the only way back to it.

    Cached — like get_taxonomy/get_graph, called at both concept-filter-generation and
    (taxonomy-scheme) mapping stages within a single run. Graph hashes/compares by
    identity, and get_graph is itself cached per community, so this correctly hits for
    repeat calls on the same community within a run.

    :param graph: the taxonomy's rdflib Graph, as returned by get_graph
    :return: the taxonomy's concepts, indexed with local references with IRI resolution
    """
    scheme_titles = {
        str(scheme): _first_literal(graph, scheme, DCTERMS.title)
        for scheme in graph.subjects(RDF.type, SKOS.ConceptScheme)
    }

    raw_concepts = []
    for concept in graph.subjects(RDF.type, SKOS.Concept):
        scheme = graph.value(concept, SKOS.inScheme)
        raw_concepts.append(
            {
                "iri": str(concept),
                "scheme": scheme_titles.get(str(scheme), "Other")
                if scheme
                else "Other",
                "label": _first_literal(graph, concept, SKOS.prefLabel) or "",
                "alt_labels": [str(o) for o in graph.objects(concept, SKOS.altLabel)],
                "detail": _first_literal(
                    graph, concept, SKOS.definition, SKOS.scopeNote
                ),
            }
        )
    raw_concepts.sort(key=lambda c: (c["scheme"], c["label"]))

    local_ref_to_iri: dict[str, str] = {}
    concepts: list[Concept] = []
    for i, raw_concept in enumerate(raw_concepts):
        local_ref = f"C{i}"
        local_ref_to_iri[local_ref] = raw_concept["iri"]
        concepts.append(
            Concept(
                local_ref=local_ref,
                scheme=raw_concept["scheme"],
                label=raw_concept["label"],
                alt_labels=raw_concept["alt_labels"],
                detail=raw_concept["detail"],
            )
        )

    logger.debug(
        "Indexed %d concepts across %d schemes", len(concepts), len(scheme_titles)
    )
    return IndexedVocab(concepts=concepts, local_ref_to_iri=local_ref_to_iri)
