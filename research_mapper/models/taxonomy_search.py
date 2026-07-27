from typing import Annotated

from pydantic import Field, BaseModel

from research_mapper.models.common import Evidence

IRI = Annotated[str, Field(pattern=r"^https?://")]


class Concept(BaseModel):
    """One taxonomy concept."""

    local_ref: str  # the local, simpler ID of the concept for easy LLM citation
    scheme: str
    label: str
    alt_labels: list[str] = []
    detail: str | None = None  # definition or scope_note


class ConceptFilterGroup(BaseModel):
    """One scheme's worth of selected concepts."""

    scheme: str
    concept_local_refs: list[str]
    reason: str


class IndexedVocab(BaseModel):
    """A taxonomy's concepts, indexed for LLM-facing selection and IRI resolution."""

    concepts: list[Concept]
    local_ref_to_iri: dict[str, IRI]

    def resolve(self, local_refs: list[str]) -> list[IRI]:
        """
        Resolves local_refs back to their concept IRIs.
        :param local_refs: the local_refs to resolve, e.g. from a ConceptFilterGroup
        :return: the corresponding concept IRIs
        :raises KeyError: if a local_ref isn't part of this index
        """
        return [self.local_ref_to_iri[ref] for ref in local_refs]


class ConceptSearchPage(BaseModel):
    """One page of evidence retrieved via concept filters, with pagination metadata."""

    evidence: list[Evidence]
    total_count: int
    is_total_lower_bound: bool
