import uuid

import pytest

from factories import make_operation, make_session, make_user
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.views import (
    CoordinateRow,
    RefRow,
    ScreeningRow,
)

ONE = uuid.UUID("11111111-1111-1111-1111-111111111111")
TWO = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def ctx(db, session_factory):
    user = make_user(db)
    session = make_session(db, user)
    return EvidenceMapContext(make_operation(db, session, user).id, session_factory)


def stored(db, destiny_id) -> SessionReference:
    db.expire_all()
    return db.query(SessionReference).filter_by(destiny_id=destiny_id).one()


def test_recording_the_same_reference_twice_appends_provenance(db, ctx):
    ctx.record_references([RefRow(ONE, {"query": "a"}), RefRow(TWO, {"query": "a"})])
    ctx.record_references([RefRow(ONE, {"query": "b"})])

    assert db.query(SessionReference).count() == 2
    assert stored(db, ONE).provenance == [{"query": "a"}, {"query": "b"}]
    assert stored(db, ONE).stage == SessionReferenceStage.GATHERED


def test_screening_moves_references_in_and_out(db, ctx):
    ctx.record_references([RefRow(ONE, {}), RefRow(TWO, {})])
    ctx.set_screening(
        [
            ScreeningRow(ONE, include=True, reasoning="on topic", criteria_version=1),
            ScreeningRow(TWO, include=False, reasoning="off topic", criteria_version=1),
        ]
    )

    assert stored(db, ONE).stage == SessionReferenceStage.INCLUDED
    assert stored(db, TWO).stage == SessionReferenceStage.EXCLUDED
    assert stored(db, ONE).screening["reasoning"] == "on topic"
    assert stored(db, ONE).screening["by"] == "agent"


def test_coordinates_mark_references_mapped(db, ctx):
    ctx.record_references([RefRow(ONE, {})])
    ctx.set_coordinates(
        [CoordinateRow(ONE, {"sector": ["energy"]}, "clear", dimensions_version=2)]
    )

    assert stored(db, ONE).stage == SessionReferenceStage.MAPPED
    assert stored(db, ONE).coordinate == {"sector": ["energy"]}
    assert stored(db, ONE).mapping["dimensions_version"] == 2


def test_mark_failed_touches_only_the_ids_given(db, ctx):
    ctx.record_references([RefRow(ONE, {}), RefRow(TWO, {})])
    ctx.mark_failed([ONE])

    assert stored(db, ONE).stage == SessionReferenceStage.FAILED
    assert stored(db, TWO).stage == SessionReferenceStage.GATHERED


def test_references_can_be_filtered_by_stage(ctx):
    ctx.record_references([RefRow(ONE, {}), RefRow(TWO, {})])
    ctx.mark_failed([TWO])

    assert {r.destiny_id for r in ctx.references()} == {ONE, TWO}
    gathered = ctx.references(SessionReferenceStage.GATHERED)
    assert [r.destiny_id for r in gathered] == [ONE]
