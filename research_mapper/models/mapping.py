from pydantic import BaseModel

from research_mapper.models.common import Evidence


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
    """
    A piece of Evidence paired with its coordinate in a map, where `coordinate` maps each mapping
    dimension's name to the name(s) of the subtopic(s) the evidence belongs to within that
    dimension — usually one, but an evidence item annotated with multiple concepts within a
    single taxonomy scheme legitimately belongs to more than one subtopic there.
    """

    evidence: Evidence
    coordinate: dict[str, list[str]]


class EvidenceMap(BaseModel):
    """
    A collection of MappedEvidence objects together with the mapping dimensions (and their
    subtopics) they were mapped across.
    """

    mapped_evidence: list[MappedEvidence]
    dimensions: tuple[
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
        MappingDimensionWithSubTopics,
    ]
