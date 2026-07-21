"""Adapters for translating DESTINY SDK types into research-mapper's domain models."""

from destiny_sdk.enhancements import EnhancementType
from destiny_sdk.references import Reference

from research_mapper.models.common import Evidence


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
    metadata["pdf_urls"] = pdf_urls
    metadata["landing_page_urls"] = landing_page_urls

    return Evidence(**metadata)
