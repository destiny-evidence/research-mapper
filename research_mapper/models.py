from enum import StrEnum, auto
from typing import Self

from destiny_sdk.core import UUID
from destiny_sdk.enhancements import (
    EnhancementType,
    Pagination,
    PublicationVenue,
    PublicationVenueType,
)
from destiny_sdk.identifiers import ExternalIdentifier, ExternalIdentifierType
from destiny_sdk.references import Reference
from luqum import parser
from luqum.exceptions import ParseSyntaxError
from pydantic import BaseModel, Field, field_validator


class UserQuery(BaseModel):
    query: str


class LuceneQuery(BaseModel):
    """Validated Lucene query model."""

    query: str = Field(description="A valid Lucene query syntax string")

    @field_validator("query")
    @classmethod
    def validate_lucene_syntax(cls, v: str) -> str:
        """Validate that the query is valid Lucene syntax."""
        try:
            parser.parse(v)
            return v
        except ParseSyntaxError as e:
            raise ValueError(f"Invalid Lucene syntax: {e}") from e

    def __hash__(self) -> int:
        return hash(self.query)

    def __str__(self) -> str:
        return self.query


_DESTINY_VENUE_TYPE_TO_RIS: dict[PublicationVenueType, str] = {
    PublicationVenueType.JOURNAL: "JOUR",
    PublicationVenueType.REPOSITORY: "RPRT",
    PublicationVenueType.CONFERENCE: "CONF",
    PublicationVenueType.EBOOK_PLATFORM: "EBOOK",
    PublicationVenueType.BOOK_SERIES: "BOOK",
    PublicationVenueType.OTHER: "GEN",
}


class Evidence(BaseModel):
    destiny_id: UUID
    external_identifiers: list[ExternalIdentifier] = []
    title: str | None = None
    abstract: str | None = None
    authors: list[str] = []
    year: int | None = None
    pdf_urls: list[str] = []
    landing_page_urls: list[str] = []
    publisher: str | None = None
    publication_venue: PublicationVenue | None = None
    pagination: Pagination | None = None

    def __hash__(self) -> int:
        return hash(
            (self.destiny_id, str([id.identifier for id in self.external_identifiers]))
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Evidence):
            return NotImplemented
        return hash(self) == hash(other)

    def __str__(self) -> str:
        title = self.title or ""
        abstract = self.abstract or ""
        if title or abstract:
            return f"{title} - {abstract}"
        return str(self.destiny_id)

    def as_ris_entry(self) -> dict:
        """Serialise this Evidence instance to a rispy-compatible RIS entry dict."""
        venue_type = (
            self.publication_venue.venue_type if self.publication_venue else None
        )
        entry: dict = {
            "type_of_reference": _DESTINY_VENUE_TYPE_TO_RIS.get(venue_type, "GEN")
            if venue_type
            else "GEN",
            "id": str(self.destiny_id),
        }

        if self.title:
            entry["title"] = self.title
        if self.abstract:
            entry["abstract"] = self.abstract
        if self.authors:
            entry["authors"] = self.authors
        if self.year:
            entry["year"] = str(self.year)
        if self.publisher:
            entry["publisher"] = self.publisher

        if self.publication_venue:
            if self.publication_venue.display_name:
                entry["journal_name"] = self.publication_venue.display_name
            if self.publication_venue.issn:
                entry["issn"] = self.publication_venue.issn[0]

        if self.pagination:
            if self.pagination.volume:
                entry["volume"] = self.pagination.volume
            if self.pagination.issue:
                entry["number"] = self.pagination.issue
            if self.pagination.first_page:
                entry["start_page"] = self.pagination.first_page
            if self.pagination.last_page:
                entry["end_page"] = self.pagination.last_page

        for ext_id in self.external_identifiers:
            if ext_id.identifier_type == ExternalIdentifierType.DOI:
                entry["doi"] = str(ext_id.identifier)
                break

        for ext_id in self.external_identifiers:
            if ext_id.identifier_type == ExternalIdentifierType.PM_ID:
                entry["accession_number"] = str(ext_id.identifier)
                break

        urls = self.landing_page_urls or self.pdf_urls
        if urls:
            entry["urls"] = urls

        return entry

    @classmethod
    def from_destiny_reference(cls, ref: Reference) -> Self:
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

        return cls(**metadata)


class ScreeningCriterionType(StrEnum):
    INCLUSION = auto()
    EXCLUSION = auto()


class ScreeningCriterion(BaseModel):
    criterion_type: ScreeningCriterionType
    description: str

    def __str__(self) -> str:
        return f"{self.criterion_type.value.capitalize()} - {self.description}"


class DimensionSubTopic(BaseModel):
    name: str
    description: str


class MappingDimension(BaseModel):
    name: str
    description: str

    def __str__(self) -> str:
        return f"{self.name} - {self.description}"

    def __hash__(self) -> int:
        return hash(str(self))


class MappingDimensionWithSubTopics(MappingDimension):
    subtopics: list[DimensionSubTopic]


class MappedEvidence(BaseModel):
    evidence: Evidence
    coordinate: dict[str, str]
