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


def flat(batches) -> list:
    return [row for batch in batches for row in batch]


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


def test_references_carry_the_verdicts_a_later_step_needs(db, ctx):
    """screen_evidence and generate_map resume by skipping rows that already have one."""
    ctx.record_references([RefRow(ONE, {}), RefRow(TWO, {})])
    ctx.set_screening(
        [ScreeningRow(ONE, include=True, reasoning="on topic", criteria_version=1)]
    )
    ctx.set_coordinates([CoordinateRow(ONE, {"sector": ["energy"]}, "clear", 2)])

    by_id = {row.destiny_id: row for row in flat(ctx.reference_batches())}

    assert by_id[ONE].screening["include"] is True
    assert by_id[ONE].coordinate == {"sector": ["energy"]}
    assert by_id[TWO].screening is None
    assert by_id[TWO].coordinate is None


def test_references_can_be_filtered_by_stage(ctx):
    ctx.record_references([RefRow(ONE, {}), RefRow(TWO, {})])
    ctx.mark_failed([TWO])

    assert {r.destiny_id for r in flat(ctx.reference_batches())} == {ONE, TWO}
    gathered = flat(ctx.reference_batches(SessionReferenceStage.GATHERED))
    assert [r.destiny_id for r in gathered] == [ONE]


MANY = [uuid.UUID(int=n) for n in range(1, 8)]


def test_batches_cover_every_row_once_in_id_order(ctx):
    ctx.record_references([RefRow(destiny_id, {}) for destiny_id in MANY])

    batches = list(ctx.reference_batches(size=3))

    assert [len(batch) for batch in batches] == [3, 3, 1]
    ids = [row.destiny_id for row in flat(batches)]
    assert sorted(ids) == sorted(MANY)
    assert len(set(ids)) == len(MANY)


def test_a_step_moving_rows_on_mid_run_still_sees_each_once(ctx):
    """Screening moves what it screens out of GATHERED as it goes, and leaves what it
    failed on: neither may shift a batch, or come round again."""
    ctx.record_references([RefRow(destiny_id, {}) for destiny_id in MANY])
    seen = []
    for batch in ctx.reference_batches(SessionReferenceStage.GATHERED, size=2):
        seen += [row.destiny_id for row in batch]
        # Screen all but the first of each batch, which "fails" and stays GATHERED.
        ctx.set_screening(
            [
                ScreeningRow(row.destiny_id, True, "on topic", criteria_version=1)
                for row in batch[1:]
            ]
        )

    assert sorted(seen) == sorted(MANY)
    assert len(seen) == len(MANY)


def test_counts_come_from_the_database(ctx):
    screened_in(ctx, ONE, TWO)
    ctx.record_references([RefRow(MANY[0], {})])
    ctx.set_coordinates(
        [CoordinateRow(ONE, {"Setting": ["Urban"]}, "urban", dimensions_version=1)]
    )

    assert ctx.count_references(SessionReferenceStage.GATHERED) == 1
    assert (
        ctx.count_references(
            SessionReferenceStage.INCLUDED, SessionReferenceStage.MAPPED
        )
        == 2
    )
    assert ctx.count_screened_in() == 2
    assert ctx.count_to_map(1) == 1
    assert ctx.count_to_map(2) == 2


def screened_in(ctx, *destiny_ids):
    """Put every id through screening, so they land at INCLUDED."""
    ctx.record_references([RefRow(destiny_id, {}) for destiny_id in destiny_ids])
    ctx.set_screening(
        [
            ScreeningRow(
                destiny_id, include=True, reasoning="on topic", criteria_version=1
            )
            for destiny_id in destiny_ids
        ]
    )


def test_a_fresh_run_has_every_screened_in_reference_to_map(ctx):
    screened_in(ctx, ONE, TWO)

    assert {r.destiny_id for r in flat(ctx.batches_to_map(1))} == {ONE, TWO}
    assert ctx.count_mapped_at(1) == 0


def test_a_retry_skips_what_the_failed_attempt_already_placed(ctx):
    """The whole point of not simply reading INCLUDED|MAPPED: resuming stays cheap."""
    screened_in(ctx, ONE, TWO)
    ctx.set_coordinates(
        [CoordinateRow(ONE, {"Setting": ["Urban"]}, "urban", dimensions_version=1)]
    )

    assert [r.destiny_id for r in flat(ctx.batches_to_map(1))] == [TWO]
    assert ctx.count_mapped_at(1) == 1


def test_bumping_the_dimensions_brings_placed_references_back(ctx):
    """Reading INCLUDED alone stranded these: no step would ever revisit them."""
    screened_in(ctx, ONE, TWO)
    ctx.set_coordinates(
        [
            CoordinateRow(ONE, {"Setting": ["Urban"]}, "urban", dimensions_version=1),
            CoordinateRow(TWO, {"Setting": ["Rural"]}, "rural", dimensions_version=1),
        ]
    )

    assert {r.destiny_id for r in flat(ctx.batches_to_map(2))} == {ONE, TWO}
    assert ctx.count_mapped_at(2) == 0, "nothing is placed against the new dimensions"


def test_an_excluded_reference_is_never_up_for_mapping(ctx):
    ctx.record_references([RefRow(ONE, {}), RefRow(TWO, {})])
    ctx.set_screening(
        [
            ScreeningRow(ONE, include=True, reasoning="on topic", criteria_version=1),
            ScreeningRow(TWO, include=False, reasoning="off topic", criteria_version=1),
        ]
    )

    assert [r.destiny_id for r in flat(ctx.batches_to_map(1))] == [ONE]
    assert [r.destiny_id for r in flat(ctx.screened_in_batches())] == [ONE]


def test_screened_in_ignores_what_was_already_placed(ctx):
    """The taxonomy tail writes fresh dimensions, so it re-places everything."""
    screened_in(ctx, ONE, TWO)
    ctx.set_coordinates(
        [CoordinateRow(ONE, {"Scheme": ["A"]}, "a", dimensions_version=1)]
    )

    assert {r.destiny_id for r in flat(ctx.screened_in_batches())} == {ONE, TWO}


def test_the_workflow_declares_this_context():
    """The worker builds contexts from the registry, so the pairing lives there."""
    from research_mapper import workflows

    assert workflows.WORKFLOWS["evidence_map"].context is EvidenceMapContext
