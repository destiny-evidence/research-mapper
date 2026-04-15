import uuid

from destiny_sdk.enhancements import EnhancementType
from destiny_sdk.identifiers import ExternalIdentifier
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


class Evidence(BaseModel):
    destiny_id: uuid.UUID
    external_identifiers: list[ExternalIdentifier] = []
    title: str | None = None
    abstract: str | None = None
    authors: list[str] = []
    year: int | None = None
    pdf_urls: list[str] = []

    def __hash__(self) -> int:
        return hash(
            (self.destiny_id, str([id.identifier for id in self.external_identifiers]))
        )

    @classmethod
    def from_destiny_reference(cls, ref: Reference):
        metadata = {
            "destiny_id": ref.id,
            # extract identifiers
            "external_identifiers": ref.identifiers,
        }

        # extract enhancements
        pdf_urls = []
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
                case EnhancementType.ABSTRACT:
                    metadata["abstract"] = str(content.abstract)
                case EnhancementType.LOCATION:
                    pdf_urls += [
                        str(location.pdf_url)
                        for location in content.locations
                        if location.pdf_url is not None
                    ]
        metadata["pdf_urls"] = pdf_urls

        return cls(**metadata)
