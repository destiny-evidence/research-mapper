from pydantic import BaseModel, Field

from research_mapper.models.common import IRI, Evidence


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


class ConceptSummary(BaseModel):
    """
    Enough to cite and recognise a concept — returned by the taxonomy browsing
    tools (listing/search/broader/narrower) as structured data, not a
    formatted display string the agent would have to parse apart to recover
    local_ref from. `narrower_count` flags concepts that group others
    underneath them — often category headers with no definition of their
    own, rather than concepts meant to be cited directly.
    """

    local_ref: str
    label: str
    scheme: str
    narrower_count: int = 0


class ConceptDetail(ConceptSummary):
    """The full detail for one concept, returned by get_concept_detail."""

    alt_labels: list[str] = []
    detail: str | None = None


class ClarificationOptions(BaseModel):
    """A question with a fixed set of options for the user to choose from."""

    question: str = Field(description="The clarifying question to ask the user.")
    options: list[str] = Field(
        min_length=1,
        description=(
            "Concrete, mutually exclusive answer options for the user to pick from. "
            "Do not include a catch-all 'not sure' option — one is added automatically."
        ),
    )
