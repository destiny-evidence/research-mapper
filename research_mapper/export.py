"""Export Evidence collections to standard bibliographic formats."""

from typing import IO

import rispy

from research_mapper.models import Evidence


def export_to_ris(evidences: list[Evidence], file: IO[str]) -> None:
    """Write a collection of Evidence objects to an open file in RIS format."""
    rispy.dump([ev.as_ris_entry() for ev in evidences], file)
