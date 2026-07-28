"""Fetches and indexes taxonomy/vocabulary JSON-LD for concept-filter generation."""

import logging
from enum import StrEnum, auto

import httpx
from pyld import jsonld

from research_mapper.models.taxonomy_search import Concept, IndexedVocab

logger = logging.getLogger(__name__)

_SKOS = "http://www.w3.org/2004/02/skos/core#"


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


def get_taxonomy(community: RepoCommunity) -> dict:
    """
    Fetches the raw vocabulary JSON-LD document for a repository community.
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


def _literal(node: dict, predicate: str) -> str | None:
    """
    Reads a single literal (string) value off an expanded JSON-LD node.
    :param node: an expanded JSON-LD node, as produced by pyld.jsonld.expand
    :param predicate: the full predicate IRI to read, e.g. the expanded form of skos:prefLabel
    :return: the first literal value for that predicate, or None if absent
    """
    values = node.get(predicate, [])
    return values[0]["@value"] if values else None


def _ref(node: dict, predicate: str) -> str | None:
    """
    Reads a single node reference (an @id) off an expanded JSON-LD node.
    :param node: an expanded JSON-LD node, as produced by pyld.jsonld.expand
    :param predicate: the full predicate IRI to read, e.g. the expanded form of skos:inScheme
    :return: the @id of the referenced node, or None if absent
    """
    values = node.get(predicate, [])
    return values[0]["@id"] if values else None


def build_concept_index(vocab: dict) -> IndexedVocab:
    """
    Expands a vocabulary JSON-LD document and builds a flat, internal concept index.

    The returned Concepts never carry their IRI directly;
    `IndexedVocab.local_ref_to_iri`/`resolve` is the only way back to it.

    :param vocab: the raw vocabulary JSON-LD document, as returned by get_taxonomy
    :return: the taxonomy's concepts, indexed with local references with IRI resolution
    """
    expanded = jsonld.expand(vocab)

    scheme_titles = {
        node["@id"]: _literal(node, "http://purl.org/dc/terms/title")
        for node in expanded
        if _SKOS + "ConceptScheme" in node.get("@type", [])
    }

    raw_concepts = [
        {
            "iri": node["@id"],
            "scheme": scheme_titles.get(_ref(node, _SKOS + "inScheme")) or "Other",
            "label": _literal(node, _SKOS + "prefLabel") or "",
            "alt_labels": [v["@value"] for v in node.get(_SKOS + "altLabel", [])],
            "detail": (
                _literal(node, _SKOS + "definition")
                or _literal(node, _SKOS + "scopeNote")
            ),
        }
        for node in expanded
        if _SKOS + "Concept" in node.get("@type", [])
    ]
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
