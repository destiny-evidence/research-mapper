"""What each of this workflow's artifacts is called and what it holds."""

from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel

from research_mapper.engine.views import ArtifactSpec
from research_mapper.models.common import IRI
from research_mapper.models.mapping import (
    MappingDimension,
    MappingDimensionWithSubTopics,
)
from research_mapper.models.screening import ScreeningCriterion
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.taxonomy import RepoCommunity


DIMENSION_COUNT = 3


class ArtifactType(StrEnum):
    SUGGESTED_SEARCH_QUERIES = auto()
    SEARCH_QUERIES = auto()
    SUGGESTED_SCREENING_CRITERIA = auto()
    SCREENING_CRITERIA = auto()
    SUGGESTED_CONCEPT_FILTERS = auto()
    CONCEPT_FILTERS = auto()
    SUGGESTED_MAP_DIMENSIONS = auto()
    MAP_DIMENSIONS = auto()
    SUGGESTED_DIMENSION_SUBTOPICS = auto()
    DIMENSIONS = auto()


class SearchQueries(BaseModel):
    queries: list[LuceneQuery]
    reasoning: str = ""


class ScreeningCriteria(BaseModel):
    criteria: list[ScreeningCriterion]
    reasoning: str = ""


class ConceptFilter(BaseModel):
    scheme: str
    concept_local_refs: list[str]
    reason: str
    labels: list[str]
    concepts: list[IRI]


class ConceptFilters(BaseModel):
    community: RepoCommunity
    groups: list[ConceptFilter]
    reasoning: str = ""


class MapDimensions(BaseModel):
    dimensions: list[MappingDimension]
    reasoning: str = ""


class Dimensions(BaseModel):
    dimensions: list[MappingDimensionWithSubTopics]
    reasoning: str = ""


SUGGESTED_SEARCH_QUERIES = ArtifactSpec(
    ArtifactType.SUGGESTED_SEARCH_QUERIES, SearchQueries
)
SEARCH_QUERIES = ArtifactSpec(ArtifactType.SEARCH_QUERIES, SearchQueries)
SUGGESTED_SCREENING_CRITERIA = ArtifactSpec(
    ArtifactType.SUGGESTED_SCREENING_CRITERIA, ScreeningCriteria
)
SCREENING_CRITERIA = ArtifactSpec(ArtifactType.SCREENING_CRITERIA, ScreeningCriteria)
SUGGESTED_CONCEPT_FILTERS = ArtifactSpec(
    ArtifactType.SUGGESTED_CONCEPT_FILTERS, ConceptFilters
)
CONCEPT_FILTERS = ArtifactSpec(ArtifactType.CONCEPT_FILTERS, ConceptFilters)
SUGGESTED_MAP_DIMENSIONS = ArtifactSpec(
    ArtifactType.SUGGESTED_MAP_DIMENSIONS, MapDimensions
)
MAP_DIMENSIONS = ArtifactSpec(ArtifactType.MAP_DIMENSIONS, MapDimensions)
SUGGESTED_DIMENSION_SUBTOPICS = ArtifactSpec(
    ArtifactType.SUGGESTED_DIMENSION_SUBTOPICS, Dimensions
)
DIMENSIONS = ArtifactSpec(ArtifactType.DIMENSIONS, Dimensions)

# Any, not BaseModel: the manifest is heterogeneous, and mypy versions disagree about
# whether ArtifactSpec is covariant in its model. The engine types a spec's name as a
# plain str, so narrow it back to this workflow's vocabulary here.
ARTIFACTS: dict[ArtifactType, ArtifactSpec[Any]] = {
    ArtifactType(spec.name): spec
    for spec in (
        SUGGESTED_SEARCH_QUERIES,
        SEARCH_QUERIES,
        SUGGESTED_SCREENING_CRITERIA,
        SCREENING_CRITERIA,
        SUGGESTED_CONCEPT_FILTERS,
        CONCEPT_FILTERS,
        SUGGESTED_MAP_DIMENSIONS,
        MAP_DIMENSIONS,
        SUGGESTED_DIMENSION_SUBTOPICS,
        DIMENSIONS,
    )
}
