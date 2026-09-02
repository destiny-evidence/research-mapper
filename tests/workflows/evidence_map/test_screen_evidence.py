import uuid

import dspy
import pytest

from factories import make_operation, make_reference, make_session, make_user
from research_mapper.engine.models import Operation
from research_mapper.engine.views import Progress
from research_mapper.models.common import Evidence
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference
from research_mapper.workflows.evidence_map.steps import screening

IDS = [
    uuid.UUID(f"{d * 8}-{d * 4}-4{d * 3}-8{d * 3}-{d * 12}")
    for d in (str(n) for n in range(1, 6))
]

CRITERIA = {
    "criteria": [{"criterion_type": "inclusion", "description": "peer reviewed"}]
}


@pytest.fixture
def session(db):
    return make_session(db, make_user(db))


@pytest.fixture
def ctx(db, session, session_factory):
    ctx = EvidenceMapContext(
        make_operation(db, session, make_user(db, "runner"), type="screen_evidence").id,
        session_factory,
    )
    ctx.write_artifact(
        artifacts.SCREENING_CRITERIA,
        artifacts.ScreeningCriteria.model_validate(CRITERIA),
    )
    return ctx


def pages(monkeypatch, *page_sizes: int) -> None:
    """Hand the step its evidence in pages, standing in for the DESTINY lookup."""
    ids = list(IDS)
    batches, start = [], 0
    for size in page_sizes:
        batches.append(ids[start : start + size])
        start += size

    def fake_get_evidence(reference_ids):
        wanted = set(reference_ids)
        for batch in batches:
            page = {
                i: Evidence(destiny_id=i, title=f"paper {i}")
                for i in batch
                if i in wanted
            }
            if page:
                yield page

    monkeypatch.setattr(screening, "get_evidence", fake_get_evidence)


def screen(monkeypatch, exclude=(), fail=()) -> None:
    """Stand in for the LM: include everything except what the test names."""

    def fake_call(self, evidence, **_):
        if evidence.destiny_id in fail:
            raise RuntimeError("the model fell over")
        return dspy.Prediction(
            include=evidence.destiny_id not in exclude, reasoning="because"
        )

    monkeypatch.setattr(screening.EvidenceScreener, "__call__", fake_call)


def run(ctx) -> dict:
    return screening.ScreenEvidence().run(ctx, screening.ScreenEvidenceParams())


def current_progress(db, ctx) -> Progress:
    db.expire_all()
    operation = db.get(Operation, ctx.operation_id)
    assert operation is not None
    return operation.progress


def stages(db, session) -> dict[uuid.UUID, SessionReferenceStage]:
    rows = db.query(SessionReference).filter_by(research_session_id=session.id).all()
    return {row.destiny_id: row.stage for row in rows}


def test_screens_every_gathered_reference_across_pages(db, ctx, session, monkeypatch):
    for destiny_id in IDS:
        make_reference(db, session, destiny_id)
    pages(monkeypatch, 3, 2)
    screen(monkeypatch, exclude={IDS[0]})

    assert run(ctx) == {"screened": 5, "included": 4, "failed": 0}

    by_id = stages(db, session)
    assert by_id[IDS[0]] == SessionReferenceStage.EXCLUDED
    assert all(by_id[i] == SessionReferenceStage.INCLUDED for i in IDS[1:])
    assert current_progress(db, ctx) == Progress(
        done=5, total=5, note="screening evidence"
    )


def test_the_criteria_version_is_stamped_on_each_verdict(db, ctx, session, monkeypatch):
    """The verdict has to say which criteria produced it, or a rerun is unreadable."""
    make_reference(db, session, IDS[0])
    ctx.write_artifact(
        artifacts.SCREENING_CRITERIA,
        artifacts.ScreeningCriteria.model_validate(CRITERIA),
    )
    pages(monkeypatch, 1)
    screen(monkeypatch)

    run(ctx)

    row = db.query(SessionReference).filter_by(destiny_id=IDS[0]).one()
    assert row.screening["criteria_version"] == 2
    assert row.screening["include"] is True
    assert row.screening["by"] == "agent"


def test_a_failed_item_stays_gathered_so_a_rerun_retries_it(
    db, ctx, session, monkeypatch
):
    for destiny_id in IDS[:3]:
        make_reference(db, session, destiny_id)
    pages(monkeypatch, 3)
    screen(monkeypatch, fail={IDS[1]})

    assert run(ctx) == {"screened": 3, "included": 2, "failed": 1}
    assert stages(db, session)[IDS[1]] == SessionReferenceStage.GATHERED


def test_a_rerun_only_screens_what_is_left_and_progress_includes_the_rest(
    db, ctx, session, monkeypatch
):
    """The resumption case: two of five already screened, so report 3/5 -> 5/5.

    Both counts are session-wide, so they stay comparable across a resumed run.
    """
    for destiny_id in IDS:
        make_reference(db, session, destiny_id)
    for destiny_id in IDS[:2]:
        db.query(SessionReference).filter_by(destiny_id=destiny_id).update(
            {"stage": SessionReferenceStage.INCLUDED}
        )
    db.commit()

    seen: set[uuid.UUID] = set()

    def fake_call(self, evidence, **_):
        seen.add(evidence.destiny_id)
        return dspy.Prediction(include=True, reasoning="because")

    pages(monkeypatch, 3, 2)
    monkeypatch.setattr(screening.EvidenceScreener, "__call__", fake_call)

    assert run(ctx) == {"screened": 5, "included": 5, "failed": 0}
    assert seen == set(IDS[2:]), "already-screened references must not rescreen"
    assert current_progress(db, ctx) == Progress(
        done=5, total=5, note="screening evidence"
    )


def test_a_session_with_nothing_gathered_fails_rather_than_screening_nothing(
    db, ctx, monkeypatch
):
    """The orchestrator refused to continue past an empty funnel; so does this."""
    pages(monkeypatch)
    screen(monkeypatch)

    with pytest.raises(screening.NothingToScreen, match="nothing to screen"):
        run(ctx)


def test_screening_needs_its_criteria_first(db, session, session_factory, monkeypatch):
    bare = EvidenceMapContext(
        make_operation(db, session, make_user(db, "other"), type="screen_evidence").id,
        session_factory,
    )
    with pytest.raises(LookupError, match=artifacts.ArtifactType.SCREENING_CRITERIA):
        run(bare)
