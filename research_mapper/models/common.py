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


class EvidencePage(BaseModel):
    """One page of full Evidence records, with pagination metadata — the raw
    page a retrieval tool accumulates internally before trimming it down to
    a RetrievalPageResult for the agent to actually read."""

    evidence: list[Evidence]
    total_count: int
    is_total_lower_bound: bool


class EvidenceSummary(BaseModel):
    """
    Enough for a retrieval agent to judge a study's relevance and decide
    whether to keep paginating — not the full Evidence record (identifiers,
    URLs, pagination metadata), which it has no use for and which downstream
    code reads off the accumulated Evidence objects directly, not this.
    """

    title: str | None = None
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> "EvidenceSummary":
        return cls(
            title=evidence.title,
            abstract=evidence.abstract,
            year=evidence.year,
            venue=evidence.publication_venue.display_name
            if evidence.publication_venue
            else None,
        )


class RetrievalPageResult(BaseModel):
    """
    One page of evidence, structured for a retrieval agent to read directly —
    title/abstract/year/venue per result, plus pagination metadata. Replaces
    a formatted count-only string (which gave no way to judge relevance) or a
    bare list of full Evidence objects (which gave too much, unrelated to
    that judgment).
    """

    results: list[EvidenceSummary]
    total_count: int
    is_total_lower_bound: bool

    @classmethod
    def from_page(cls, page: EvidencePage) -> "RetrievalPageResult":
        return cls(
            results=[EvidenceSummary.from_evidence(ev) for ev in page.evidence],
            total_count=page.total_count,
            is_total_lower_bound=page.is_total_lower_bound,
        )
