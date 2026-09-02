"""Every step this workflow can run."""

from research_mapper.engine.registry import Step
from research_mapper.workflows.evidence_map.steps.concept_filters import (
    GenerateConceptFilters,
)
from research_mapper.workflows.evidence_map.steps.sparse_query import EnhanceSparseQuery

STEPS: list[type[Step]] = [
    EnhanceSparseQuery,
    GenerateConceptFilters,
]
