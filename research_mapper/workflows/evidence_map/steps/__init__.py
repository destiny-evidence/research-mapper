from research_mapper.engine.registry import Step
from research_mapper.workflows.evidence_map.steps.concept_filters import (
    GenerateConceptFilters,
)
from research_mapper.workflows.evidence_map.steps.mapping import (
    GenerateMap,
    GenerateMapDimensions,
    GenerateMapSubtopics,
)
from research_mapper.workflows.evidence_map.steps.retrieve import (
    RetrieveConceptEvidence,
    RetrieveSparseEvidence,
)
from research_mapper.workflows.evidence_map.steps.screening import (
    GenerateScreeningCriteria,
    ScreenEvidence,
)
from research_mapper.workflows.evidence_map.steps.sparse_query import EnhanceSparseQuery
from research_mapper.workflows.evidence_map.steps.taxonomy_mapping import (
    GenerateTaxonomyMap,
)

STEPS: list[type[Step]] = [
    EnhanceSparseQuery,
    GenerateConceptFilters,
    RetrieveSparseEvidence,
    RetrieveConceptEvidence,
    GenerateScreeningCriteria,
    ScreenEvidence,
    GenerateMapDimensions,
    GenerateMapSubtopics,
    GenerateMap,
    GenerateTaxonomyMap,
]
