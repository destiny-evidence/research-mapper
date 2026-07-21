from luqum import parser
from luqum.exceptions import ParseSyntaxError
from pydantic import BaseModel, Field, field_validator


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
