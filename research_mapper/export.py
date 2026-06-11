"""Export Evidence collections to standard bibliographic formats."""

from typing import IO

import rispy

from research_mapper.models import Evidence, MappedEvidence


def export_evidence_to_ris(evidences: list[Evidence], file: IO[str]) -> None:
    """Write a collection of Evidence objects to an open file in RIS format."""
    rispy.dump([ev.as_ris_entry() for ev in evidences], file)


def export_mapped_evidence_to_ris(
    mapped_evidence: list[MappedEvidence], file: IO[str]
) -> None:
    """
    Write a collection of MappedEvidence objects to an open file in RIS format, attaching
    each item's evidence map coordinate as keywords.
    """
    rispy.dump([item.as_ris_entry() for item in mapped_evidence], file)
