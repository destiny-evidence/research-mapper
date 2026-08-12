"""Export Evidence collections to standard bibliographic formats."""

from typing import IO

import rispy
from destiny_sdk.identifiers import ExternalIdentifierType
from destiny_sdk.enhancements import PublicationVenueType

from research_mapper.models.common import Evidence
from research_mapper.models.mapping import MappedEvidence

_DESTINY_VENUE_TYPE_TO_RIS: dict[PublicationVenueType, str] = {
    PublicationVenueType.JOURNAL: "JOUR",
    PublicationVenueType.REPOSITORY: "RPRT",
    PublicationVenueType.CONFERENCE: "CONF",
    PublicationVenueType.EBOOK_PLATFORM: "EBOOK",
    PublicationVenueType.BOOK_SERIES: "BOOK",
    PublicationVenueType.OTHER: "GEN",
}


def evidence_to_ris_entry(
    evidence: Evidence, keywords: list[str] | None = None
) -> dict:
    """
    Serialise an Evidence instance to a rispy-compatible RIS entry dict.
    :param evidence: the Evidence instance to serialise
    :param keywords: optional collection of keywords to attach to the entry, so they
        can be filtered/grouped on after import.
    """
    venue_type = (
        evidence.publication_venue.venue_type if evidence.publication_venue else None
    )
    entry: dict = {
        "type_of_reference": _DESTINY_VENUE_TYPE_TO_RIS.get(venue_type, "GEN")
        if venue_type
        else "GEN",
        "id": str(evidence.destiny_id),
    }

    if keywords:
        entry["keywords"] = keywords

    if evidence.title:
        entry["title"] = evidence.title
    if evidence.abstract:
        entry["abstract"] = evidence.abstract
    if evidence.authors:
        entry["authors"] = evidence.authors
    if evidence.year:
        entry["year"] = str(evidence.year)
    if evidence.publisher:
        entry["publisher"] = evidence.publisher

    if evidence.publication_venue:
        if evidence.publication_venue.display_name:
            entry["journal_name"] = evidence.publication_venue.display_name
        if evidence.publication_venue.issn:
            entry["issn"] = evidence.publication_venue.issn[0]

    if evidence.pagination:
        if evidence.pagination.volume:
            entry["volume"] = evidence.pagination.volume
        if evidence.pagination.issue:
            entry["number"] = evidence.pagination.issue
        if evidence.pagination.first_page:
            entry["start_page"] = evidence.pagination.first_page
        if evidence.pagination.last_page:
            entry["end_page"] = evidence.pagination.last_page

    for ext_id in evidence.external_identifiers:
        if ext_id.identifier_type == ExternalIdentifierType.DOI:
            entry["doi"] = str(ext_id.identifier)
            break

    for ext_id in evidence.external_identifiers:
        if ext_id.identifier_type == ExternalIdentifierType.PM_ID:
            entry["accession_number"] = str(ext_id.identifier)
            break

    urls = evidence.landing_page_urls or evidence.pdf_urls
    if urls:
        entry["urls"] = urls

    return entry


def mapped_evidence_to_ris_entry(item: MappedEvidence) -> dict:
    """
    Serialise a MappedEvidence's underlying Evidence to a rispy-compatible RIS entry dict,
    attaching its evidence map coordinate as keywords (one per dimension/subtopic pair) so it
    can be filtered/grouped on after import.
    """
    keywords = [
        f"{dim}: {subtopic}"
        for dim, subtopics in item.coordinate.items()
        for subtopic in subtopics
    ]
    return evidence_to_ris_entry(item.evidence, keywords=keywords)


def export_evidence_to_ris(evidences: list[Evidence], file: IO[str]) -> None:
    """Write a collection of Evidence objects to an open file in RIS format."""
    rispy.dump([evidence_to_ris_entry(ev) for ev in evidences], file)


def export_mapped_evidence_to_ris(
    mapped_evidence: list[MappedEvidence], file: IO[str]
) -> None:
    """
    Write a collection of MappedEvidence objects to an open file in RIS format, attaching
    each item's evidence map coordinate as keywords.
    """
    rispy.dump([mapped_evidence_to_ris_entry(item) for item in mapped_evidence], file)
