from research_mapper.engine.registry import Step
from research_mapper.workflows.evidence_map.steps.retrieve import (
    RetrieveConceptEvidence,
    RetrieveSparseEvidence,
)
from research_mapper.workflows.evidence_map.steps.sparse_query import EnhanceSparseQuery

STEPS: list[type[Step]] = [
    EnhanceSparseQuery,
    RetrieveSparseEvidence,
    RetrieveConceptEvidence,
]
