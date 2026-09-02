"""Copying this workflow's references into a fork."""

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from research_mapper.engine.fork import Cut
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.steps.retrieve import (
    SPARSE_MODE,
    TAXONOMY_MODE,
)

MODES = {
    "retrieve_sparse_evidence": SPARSE_MODE,
    "retrieve_concept_evidence": TAXONOMY_MODE,
}
SCREENING = "screen_evidence"
MAPPING = frozenset({"generate_map", "generate_taxonomy_map"})

GATHERED = SessionReferenceStage.GATHERED
INCLUDED = SessionReferenceStage.INCLUDED
MAPPED = SessionReferenceStage.MAPPED
FAILED = SessionReferenceStage.FAILED


def _rewound(
    stage: SessionReferenceStage, screened: bool, mapped: bool
) -> SessionReferenceStage:
    """How far back a reference at this stage has to go for the cut to be true."""
    if stage is FAILED or not screened:
        return GATHERED
    if stage is MAPPED and not mapped:
        return INCLUDED
    return stage


def fork_state(db: Session, cut: Cut) -> None:
    """Copy the references a fork inherits, rewound to the stage its cut reached."""
    modes = {MODES[name] for name in cut.operation_types if name in MODES}
    if not modes:
        return
    screened = SCREENING in cut.operation_types
    mapped = bool(MAPPING & cut.operation_types)

    found = db.execute(
        select(
            SessionReference.destiny_id,
            SessionReference.stage,
            SessionReference.provenance,
            SessionReference.screening,
            SessionReference.coordinate,
            SessionReference.mapping,
        ).where(SessionReference.research_session_id == cut.source_id)
    )
    copies = []
    for reference in found:
        # A reference survives only if a retrieval that found it is in the cut,
        # and keeps only that retrieval's provenance: the rest will run again.
        kept = [entry for entry in reference.provenance if entry.get("mode") in modes]
        if not kept:
            continue
        stage = _rewound(reference.stage, screened, mapped)
        copies.append(
            {
                "research_session_id": cut.new_id,
                "destiny_id": reference.destiny_id,
                "stage": stage,
                "provenance": kept,
                "screening": None if stage is GATHERED else reference.screening,
                "coordinate": reference.coordinate if stage is MAPPED else None,
                "mapping": reference.mapping if stage is MAPPED else None,
            }
        )
    if copies:
        db.execute(insert(SessionReference), copies)
