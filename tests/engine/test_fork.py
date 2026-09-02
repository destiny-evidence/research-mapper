import uuid

import pytest
from sqlalchemy import select

from factories import make_operation, make_session, make_user
from research_mapper import workflows
from research_mapper.engine import fork
from research_mapper.engine.enums import DecisionType, OperationStatus
from research_mapper.engine.models import (
    Artifact,
    Decision,
    Operation,
)
from research_mapper.engine.runner import SessionBusy
from research_mapper.workflows.evidence_map.enums import SessionReferenceStage
from research_mapper.workflows.evidence_map.models import SessionReference

COMPLETE = OperationStatus.COMPLETE


def ask(db, operation, key="pick", answer=None):
    """Record that an operation asked something, and optionally that it was answered."""
    decision = Decision(
        research_session_id=operation.research_session_id,
        operation_id=operation.id,
        type=DecisionType.SELECT_MANY,
        key=key,
        prompt="pick some",
        options=[],
        answer=answer,
    )
    db.add(decision)
    db.commit()
    return decision


def artifact(db, operation, type, version=1, payload=None):
    row = Artifact(
        research_session_id=operation.research_session_id,
        operation_id=operation.id,
        type=type,
        version=version,
        payload=payload or {},
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def source(db):
    """A session run in PLAN order as far as choosing screening criteria."""
    user = make_user(db)
    session = make_session(db, user)

    def step(type, version):
        return make_operation(
            db, session, user, type, status=COMPLETE, version_number=version
        )

    draft = step("enhance_sparse_query", 1)
    artifact(db, draft, "suggested_search_queries")
    draft_ask = ask(db, draft, "select_queries", answer=[{"query": "a"}])
    artifact(db, draft, "search_queries")

    search = step("retrieve_sparse_evidence", 2)

    filters = step("generate_concept_filters", 3)
    artifact(db, filters, "concept_filter_loop")
    first_clarify = ask(db, filters, "clarify:3", answer=[{"option": "yes"}])
    artifact(db, filters, "concept_filter_loop", version=2)
    second_clarify = ask(db, filters, "clarify:7", answer=[{"option": "no"}])
    artifact(db, filters, "concept_filter_loop", version=3)
    artifact(db, filters, "concept_filters")

    concepts = step("retrieve_concept_evidence", 4)

    criteria = step("generate_screening_criteria", 5)
    artifact(db, criteria, "suggested_screening_criteria")
    criteria_ask = ask(db, criteria, "select_criteria", answer=[{"criterion": "x"}])
    artifact(db, criteria, "screening_criteria")

    session.head_version_number = 5
    db.commit()
    return {
        "user": user,
        "session": session,
        "draft": draft,
        "search": search,
        "filters": filters,
        "concepts": concepts,
        "criteria": criteria,
        "draft_ask": draft_ask,
        "first_clarify": first_clarify,
        "second_clarify": second_clarify,
        "criteria_ask": criteria_ask,
    }


def run(db, source, user, decision):
    return fork.fork(
        db, source, user.id, decision.id, state_factory=workflows.fork_state
    )


def operations_of(db, session_id):
    return {
        operation.type: operation
        for operation in db.execute(
            select(Operation).where(Operation.research_session_id == session_id)
        ).scalars()
    }


def artifacts_of(db, session_id):
    return {
        row.type
        for row in db.execute(
            select(Artifact).where(Artifact.research_session_id == session_id)
        ).scalars()
    }


def types_of(db, operations):
    """The artifact types each of a session's operations holds."""
    return {
        step: {
            row.type
            for row in db.execute(
                select(Artifact).where(Artifact.operation_id == operation.id)
            ).scalars()
        }
        for step, operation in operations.items()
    }


def references_of(db, session_id):
    return (
        db.execute(
            select(SessionReference).where(
                SessionReference.research_session_id == session_id
            )
        )
        .scalars()
        .all()
    )


def test_a_fork_copies_the_prefix_and_requeues_the_reopened_step(db, source, queued):
    forked = run(db, source["session"], source["user"], source["criteria_ask"])

    assert forked.forked_from_id == source["session"].id
    assert forked.forked_at_step == "generate_screening_criteria"
    assert forked.head_version_number == 4
    assert forked.question == source["session"].question

    copied = operations_of(db, forked.id)
    assert set(copied) == {
        "enhance_sparse_query",
        "retrieve_sparse_evidence",
        "generate_concept_filters",
        "retrieve_concept_evidence",
        "generate_screening_criteria",
    }
    assert copied["enhance_sparse_query"].status is COMPLETE
    reopened = copied["generate_screening_criteria"]
    assert reopened.status is OperationStatus.PENDING
    assert reopened.version_number is None
    assert queued() == [str(reopened.id)]


def test_the_reopened_step_keeps_its_suggestion_but_not_its_answer(db, source):
    forked = run(db, source["session"], source["user"], source["criteria_ask"])

    assert artifacts_of(db, forked.id) == {
        "suggested_search_queries",
        "search_queries",
        "concept_filter_loop",
        "concept_filters",
        "suggested_screening_criteria",
    }
    reopened = operations_of(db, forked.id)["generate_screening_criteria"]
    assert (
        db.execute(select(Decision).where(Decision.operation_id == reopened.id))
        .scalars()
        .all()
        == []
    )
    kept = (
        db.execute(select(Decision).where(Decision.research_session_id == forked.id))
        .scalars()
        .all()
    )
    assert [decision.key for decision in kept] == [
        "select_queries",
        "clarify:3",
        "clarify:7",
    ]
    assert kept[0].answer == [{"query": "a"}]


def test_forking_the_first_step_copies_nothing_before_it(db, source):
    forked = run(db, source["session"], source["user"], source["draft_ask"])

    assert forked.head_version_number == 0
    assert set(operations_of(db, forked.id)) == {"enhance_sparse_query"}
    assert artifacts_of(db, forked.id) == {"suggested_search_queries"}


def test_a_question_still_open_can_be_forked(db, source):
    session, user = source["session"], source["user"]
    open_step = make_operation(
        db,
        session,
        user,
        "generate_map_dimensions",
        status=OperationStatus.AWAITING_INPUT,
    )
    artifact(db, open_step, "suggested_map_dimensions")
    open_question = ask(db, open_step, "select_dimensions")

    forked = run(db, session, user, open_question)

    assert forked.head_version_number == 5
    assert "generate_map_dimensions" in operations_of(db, forked.id)


def test_forking_an_abandoned_attempt_copies_nothing_that_came_after_it(db, source):
    """Asking a step to suggest again parks the attempt it replaced, with no version."""
    session, user = source["session"], source["user"]
    abandoned = make_operation(
        db,
        session,
        user,
        "generate_map_dimensions",
        status=OperationStatus.AWAITING_INPUT,
    )
    stale = ask(db, abandoned, "select_dimensions", answer=[{"name": "a"}])
    make_operation(
        db, session, user, "screen_evidence", status=COMPLETE, version_number=6
    )

    forked = run(db, session, user, stale)

    assert "screen_evidence" not in operations_of(db, forked.id)
    assert forked.head_version_number == 5


def test_a_fork_leaves_behind_what_a_superseded_attempt_chose(db, source):
    """Suggesting again then forking must not bring back the first answer."""
    session, user = source["session"], source["user"]
    again = make_operation(
        db,
        session,
        user,
        "generate_screening_criteria",
        status=COMPLETE,
        version_number=6,
    )
    artifact(db, again, "suggested_screening_criteria", version=2)
    reopen = ask(db, again, "select_criteria", answer=[{"criterion": "y"}])
    artifact(db, again, "screening_criteria", version=2)
    session.head_version_number = 6
    db.commit()

    forked = run(db, session, user, reopen)

    reopened = operations_of(db, forked.id)["generate_screening_criteria"]
    assert {
        (row.type, row.version)
        for row in db.execute(
            select(Artifact).where(Artifact.operation_id == reopened.id)
        ).scalars()
    } == {("suggested_screening_criteria", 2)}
    assert "screening_criteria" not in artifacts_of(db, forked.id)


def test_reopening_a_later_question_keeps_the_answer_to_an_earlier_one(db, source):
    forked = run(db, source["session"], source["user"], source["second_clarify"])

    kept = (
        db.execute(select(Decision).where(Decision.research_session_id == forked.id))
        .scalars()
        .all()
    )
    assert [decision.key for decision in kept] == ["select_queries", "clarify:3"]
    reopened = operations_of(db, forked.id)["generate_concept_filters"]
    # The settled question comes across answered; the reopened one is re-asked.
    assert [
        (row.key, row.answer is not None)
        for row in db.execute(
            select(Decision)
            .where(Decision.operation_id == reopened.id)
            .order_by(Decision.id)
        ).scalars()
    ] == [("clarify:3", True)]
    versions = sorted(
        row.version
        for row in db.execute(
            select(Artifact).where(Artifact.operation_id == reopened.id)
        ).scalars()
    )
    assert versions == [1, 2]


def test_a_session_with_work_in_flight_will_not_fork(db, source):
    make_operation(
        db,
        source["session"],
        source["user"],
        "screen_evidence",
        status=OperationStatus.RUNNING,
    )
    with pytest.raises(SessionBusy):
        run(
            db,
            source["session"],
            source["user"],
            source["criteria_ask"],
        )


def test_a_decision_from_another_session_is_rejected(db, source):
    other = make_session(db, source["user"], question="different")
    stranger = make_operation(db, other, source["user"], "enhance_sparse_query")
    with pytest.raises(LookupError, match="no decision"):
        run(db, source["session"], source["user"], ask(db, stranger))


def test_the_fork_belongs_to_whoever_forked_it(db, source):
    other = make_user(db, subject="someone-else")
    forked = run(db, source["session"], other, source["criteria_ask"])

    assert forked.user_id == other.id
    copied = operations_of(db, forked.id)
    assert copied["enhance_sparse_query"].created_by_id == source["user"].id
    assert copied["generate_screening_criteria"].created_by_id == other.id


def test_a_fork_of_a_fork_points_at_its_immediate_parent(db, source):
    child = run(db, source["session"], source["user"], source["criteria_ask"])
    reopened = operations_of(db, child.id)["generate_screening_criteria"]
    reopened.status = OperationStatus.AWAITING_INPUT
    again = ask(db, reopened, "select_criteria")

    grandchild = run(db, child, source["user"], again)

    assert grandchild.forked_from_id == child.id
    assert child.forked_from_id == source["session"].id
    assert types_of(db, operations_of(db, grandchild.id)) == {
        "generate_screening_criteria": {"suggested_screening_criteria"}
    } | {
        step: types
        for step, types in types_of(db, operations_of(db, child.id)).items()
        if step != "generate_screening_criteria"
    }


def test_a_fork_of_a_fork_rewinds_a_question_it_only_ever_inherited(db, source):
    """Copies are ordered like their originals, so a rewind survives copying."""
    child = run(db, source["session"], source["user"], source["criteria_ask"])
    reopened = operations_of(db, child.id)["generate_screening_criteria"]
    reopened.status = OperationStatus.AWAITING_INPUT
    db.commit()
    inherited = db.execute(
        select(Decision)
        .where(Decision.research_session_id == child.id)
        .where(Decision.key == "clarify:3")
    ).scalar_one()

    grandchild = run(db, child, source["user"], inherited)

    loop = operations_of(db, grandchild.id)["generate_concept_filters"]
    # The loop paused once before clarify:3, so only that checkpoint comes across.
    assert [
        row.version
        for row in db.execute(
            select(Artifact).where(Artifact.operation_id == loop.id)
        ).scalars()
    ] == [1]


GATHERED = SessionReferenceStage.GATHERED
INCLUDED = SessionReferenceStage.INCLUDED
MAPPED = SessionReferenceStage.MAPPED


def reference(db, session, modes, stage=GATHERED, **kwargs):
    row = SessionReference(
        research_session_id=session.id,
        destiny_id=uuid.uuid4(),
        stage=stage,
        provenance=[{"mode": mode, "query": mode} for mode in modes],
        **kwargs,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def mapped(db, source):
    """The source, carried all the way to a finished map over both retrieval modes."""
    session, user = source["session"], source["user"]
    screen = make_operation(
        db, session, user, "screen_evidence", status=COMPLETE, version_number=6
    )
    subtopics = make_operation(
        db, session, user, "generate_map_subtopics", status=COMPLETE, version_number=7
    )
    artifact(db, subtopics, "suggested_dimension_subtopics")
    subtopics_ask = ask(db, subtopics, "edit:one", answer=[{"name": "a"}])
    place = make_operation(
        db, session, user, "generate_map", status=COMPLETE, version_number=8
    )
    session.head_version_number = 8
    db.commit()
    return {
        **source,
        "screen": screen,
        "subtopics_ask": subtopics_ask,
        "place": place,
        "sparse": reference(
            db,
            session,
            ["sparse"],
            stage=MAPPED,
            screening={"include": True},
            coordinate={"a": ["x"]},
            mapping={"dimensions_version": 1},
        ),
        "taxonomy": reference(
            db, session, ["taxonomy"], stage=INCLUDED, screening={"include": True}
        ),
        "both": reference(
            db,
            session,
            ["sparse", "taxonomy"],
            stage=INCLUDED,
            screening={"include": False},
        ),
    }


def test_forking_before_screening_rewinds_every_reference(db, mapped):
    forked = run(db, mapped["session"], mapped["user"], mapped["criteria_ask"])

    rows = references_of(db, forked.id)
    assert len(rows) == 3
    assert {row.stage for row in rows} == {GATHERED}
    assert all(row.screening is None for row in rows)
    assert all(row.coordinate is None and row.mapping is None for row in rows)


def test_forking_before_mapping_keeps_screening_but_drops_coordinates(db, mapped):
    forked = run(db, mapped["session"], mapped["user"], mapped["subtopics_ask"])

    rows = {len(row.provenance): row for row in references_of(db, forked.id)}
    assert {row.stage for row in rows.values()} == {INCLUDED}
    assert all(row.screening is not None for row in rows.values())
    assert all(row.coordinate is None and row.mapping is None for row in rows.values())


def test_forking_above_a_retrieval_drops_what_only_that_retrieval_found(db, mapped):
    forked = run(db, mapped["session"], mapped["user"], mapped["first_clarify"])

    modes = sorted(
        tuple(entry["mode"] for entry in row.provenance)
        for row in references_of(db, forked.id)
    )
    assert modes == [("sparse",), ("sparse",)]


def test_forking_above_all_retrieval_copies_no_references(db, mapped):
    forked = run(db, mapped["session"], mapped["user"], mapped["draft_ask"])

    assert references_of(db, forked.id) == []


def test_a_failed_reference_is_rewound_so_the_fork_retries_it(db, mapped):
    reference(
        db,
        mapped["session"],
        ["sparse"],
        stage=SessionReferenceStage.FAILED,
        screening={"include": True},
    )
    forked = run(db, mapped["session"], mapped["user"], mapped["subtopics_ask"])

    stages = sorted(row.stage for row in references_of(db, forked.id))
    assert stages == [GATHERED, INCLUDED, INCLUDED, INCLUDED]


def test_reopening_a_loop_step_carries_only_the_checkpoint_it_paused_on(db, source):
    forked = run(db, source["session"], source["user"], source["first_clarify"])

    reopened = operations_of(db, forked.id)["generate_concept_filters"]
    versions = sorted(
        row.version
        for row in db.execute(
            select(Artifact).where(Artifact.operation_id == reopened.id)
        ).scalars()
    )
    assert versions == [1]
    assert "concept_filters" not in artifacts_of(db, forked.id)
