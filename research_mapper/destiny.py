"""Adapters for translating DESTINY SDK types into research-mapper's domain models."""

import logging

from destiny_sdk.enhancements import EnhancementType
from destiny_sdk.references import Reference
from pyld import jsonld

from research_mapper.models.common import IRI, Evidence

logger = logging.getLogger(__name__)


def _extract_concept_iris(data: dict) -> set[IRI]:
    """
    Best-effort extraction of every concept IRI referenced anywhere in a
    LinkedDataEnhancement's JSON-LD graph. Deliberately doesn't model the graph's rich,
    nested schema (Investigation/Finding/*CodingAnnotation etc.) — just collects every
    non-blank @id after expansion; meaning (which concept, which scheme) is resolved
    later against a loaded IndexedVocab. Never raises — a malformed/unreachable
    @context degrades to "no known concepts" for this enhancement, rather than
    breaking evidence retrieval.
    :param data: the raw JSON-LD `data` field of a LinkedDataEnhancement
    :return: every non-blank @id found in the expanded graph
    """
    try:
        expanded = jsonld.expand(data)
    except Exception as exc:  # noqa: BLE001 - must never break evidence conversion
        logger.debug("Could not expand linked-data enhancement: %s", exc)
        return set()

    iris: set[str] = set()

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            node_id = node.get("@id")
            if isinstance(node_id, str) and not node_id.startswith("_:"):
                iris.add(node_id)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(expanded)
    return iris


def evidence_from_destiny_reference(ref: Reference) -> Evidence:
    """
    Parses a DESTINY SDK reference object into the 'Evidence' Domain Object.
    :param ref: the DESTINY SDK reference object
    :return: the Evidence object variant
    """
    metadata = {
        "destiny_id": ref.id,
        # extract identifiers
        "external_identifiers": ref.identifiers,
    }

    # extract enhancements
    pdf_urls = []
    landing_page_urls = []
    known_concepts: set[str] = set()
    for enhancement in ref.enhancements:
        content = enhancement.content
        match content.enhancement_type:
            case EnhancementType.BIBLIOGRAPHIC:
                if content.authorship:
                    metadata["authors"] = [
                        str(author.display_name) for author in content.authorship
                    ]
                metadata["title"] = content.title
                metadata["year"] = content.publication_year
                metadata["publisher"] = content.publisher
                metadata["publication_venue"] = content.publication_venue
                metadata["pagination"] = content.pagination
            case EnhancementType.ABSTRACT:
                metadata["abstract"] = str(content.abstract)
            case EnhancementType.LOCATION:
                pdf_urls += [
                    str(location.pdf_url)
                    for location in content.locations
                    if location.pdf_url is not None
                ]
                landing_page_urls += [
                    str(location.landing_page_url)
                    for location in content.locations
                    if location.landing_page_url is not None
                ]
            case EnhancementType.LINKED_DATA:
                known_concepts.update(_extract_concept_iris(content.data))
    metadata["pdf_urls"] = pdf_urls
    metadata["landing_page_urls"] = landing_page_urls
    metadata["known_concepts"] = sorted(known_concepts)

    return Evidence(**metadata)
