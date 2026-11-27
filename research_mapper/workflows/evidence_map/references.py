"""The views a session's references are read through, a page at a time.

Each step's table shows a subset of the session's references, sliced into buckets
(screening's verdicts, mapping's placements). Those subsets and buckets are SQL here,
so a page, its counts and its filters cost the same whatever the session's size.
"""

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import ColumnElement, String, case, type_coerce

from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference

ViewName = Literal["all", "sparse", "taxonomy", "screening", "mapping"]

_stage = SessionReference.stage


@dataclass(frozen=True)
class Slice:
    """How a view buckets its references: a SQL expression naming each one's bucket,
    and the order the buckets are shown in."""

    of: ColumnElement[str]
    order: tuple[str, ...]


STAGE = Slice(
    of=type_coerce(_stage, String()),
    order=tuple(stage.value for stage in SessionReferenceStage),
)

# Screening's verdict on a reference: its own if it has one, else what its stage says.
VERDICT = Slice(
    of=case(
        (
            SessionReference.screening.is_not(None),
            case(
                (SessionReference.screening["include"].as_boolean(), "included"),
                else_="excluded",
            ),
        ),
        (_stage == SessionReferenceStage.MAPPED, "included"),
        (_stage == SessionReferenceStage.INCLUDED, "included"),
        (_stage == SessionReferenceStage.EXCLUDED, "excluded"),
        (_stage == SessionReferenceStage.FAILED, "failed"),
        else_="not screened",
    ),
    order=("included", "excluded", "not screened", "failed"),
)

# Whether mapping has placed a reference yet.
PLACEMENT = Slice(
    of=case(
        (_stage == SessionReferenceStage.MAPPED, "mapped"),
        (_stage == SessionReferenceStage.FAILED, "failed"),
        else_="not mapped",
    ),
    order=("mapped", "not mapped", "failed"),
)


def _found_in(mode: str) -> ColumnElement[bool]:
    return SessionReference.provenance.contains([{"mode": mode}])


@dataclass(frozen=True)
class View:
    """One table's references: which of the session's, how they're bucketed, and
    which decision ("screening" or "mapping") made them, if any."""

    where: tuple[ColumnElement[bool], ...] = field(default=())
    slice: Slice | None = None
    decided: Literal["screening", "mapping"] | None = None


VIEWS: dict[str, View] = {
    "all": View(slice=STAGE),
    "sparse": View(where=(_found_in("sparse"),)),
    "taxonomy": View(where=(_found_in("taxonomy"),)),
    "screening": View(slice=VERDICT, decided="screening"),
    "mapping": View(
        where=(VERDICT.of == "included",), slice=PLACEMENT, decided="mapping"
    ),
}


def in_cell(terms: list[tuple[str, str]]) -> list[ColumnElement[bool]]:
    """References whose coordinate has each `(dimension, subtopic)`. A coordinate
    holds a list of subtopics per dimension, so containment asks for one of them."""
    return [
        SessionReference.coordinate.contains({dimension: [subtopic]})
        for dimension, subtopic in terms
    ]
