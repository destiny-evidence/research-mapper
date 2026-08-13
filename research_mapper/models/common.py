from typing import Annotated

from destiny_sdk.core import UUID
from destiny_sdk.enhancements import Pagination, PublicationVenue
from destiny_sdk.identifiers import ExternalIdentifier
from pydantic import BaseModel, Field

IRI = Annotated[str, Field(pattern=r"^https?://")]


class UserQuery(BaseModel):
    query: str


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
    known_concepts: list[IRI] = []

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
