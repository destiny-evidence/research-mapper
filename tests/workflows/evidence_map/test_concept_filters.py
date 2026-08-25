import dspy
import pytest

from factories import make_operation, make_session, make_user
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision
from research_mapper.models.react import Step as LoopStep
from research_mapper.models.taxonomy_search import (
    Concept,
    ConceptFilterGroup,
    IndexedVocab,
)
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.steps import concept_filters

CONCEPTS = [
    Concept(local_ref="C0", scheme="Topic", label="Schools"),
    Concept(local_ref="C1", scheme="Topic", label="Clinics"),
]
INDEXED = IndexedVocab(
    concepts=CONCEPTS,
    local_ref_to_iri={
        "C0": "https://vocab.example/schools",
        "C1": "https://vocab.example/clinics",
    },
)
GROUP = ConceptFilterGroup(
    scheme="Topic", concept_local_refs=["C0"], reason="the query is about schools"
)


@pytest.fixture
def operation(db):
    session = make_session(db, make_user(db))
    return make_operation(
        db, session, make_user(db, "runner"), type="generate_concept_filters"
    )


@pytest.fixture
def ctx(operation, session_factory):
    return StepContext(operation.id, session_factory)


@pytest.fixture(autouse=True)
def _taxonomy(monkeypatch):
    monkeypatch.setattr(concept_filters, "get_taxonomy", lambda community: {})
    monkeypatch.setattr(concept_filters, "build_concept_index", lambda vocab: INDEXED)


def answer(db, operation, key, value):
    db.add(
        Decision(
            research_session_id=operation.research_session_id,
            operation_id=operation.id,
            type=DecisionType.SELECT_MANY,
            key=key,
            prompt="pick",
            answer=value,
        )
    )
    db.commit()


def step(idx: int, tool: str, args: dict) -> LoopStep:
    return LoopStep(
        trajectory={f"thought_{idx}": "t", f"tool_name_{idx}": tool},
        idx=idx,
        thought="t",
        tool_name=tool,
        tool_args=args,
    )


ASK = {"request": {"question": "Which setting?", "options": ["Schools", "Clinics"]}}


def agent(monkeypatch, *results, calls=None):
    """Stand in for ResumableReAct: hand back each result in turn."""
    queue = list(results)

    class Fake:
        def start(self, **inputs):
            return queue.pop(0)

        def resume(self, step, **inputs):
            if calls is not None:
                calls.append(step)
            return queue.pop(0)

    monkeypatch.setattr(concept_filters, "build_concept_filter_agent", lambda: Fake())


def done() -> dspy.Prediction:
    return dspy.Prediction(filter_groups=[GROUP], reasoning="because")


def run(ctx) -> dict:
    return concept_filters.GenerateConceptFilters().run(
        ctx, concept_filters.GenerateConceptFiltersParams()
    )


def test_a_loop_that_never_asks_writes_its_filters(ctx, monkeypatch):
    agent(monkeypatch, done())

    assert run(ctx) == {"filter_groups": 1, "questions": 0, "version": 1}

    stored = ctx.get_artifact(artifacts.CONCEPT_FILTERS)
    assert stored is not None
    assert stored.community == "hpv"
    assert stored.groups[0].labels == ["Schools"]
    assert stored.groups[0].concepts == ["https://vocab.example/schools"]


def test_the_loop_pauses_on_a_clarifying_question_and_persists_its_step(
    ctx, monkeypatch
):
    agent(monkeypatch, step(0, "ask_for_clarification", ASK))

    with pytest.raises(NeedsInput):
        run(ctx)

    spec = ctx.pending_decisions["clarify:0"]
    assert spec.prompt == "Which setting?"
    assert [option["label"] for option in spec.options] == [
        "Schools",
        "Clinics",
        concept_filters.UNSURE,
    ]
    assert spec.constraints["exclusive"] == [{"option": concept_filters.UNSURE}]

    saved = ctx.get_artifact(artifacts.CONCEPT_FILTER_LOOP)
    assert saved is not None
    assert saved.step["idx"] == 0
    assert saved.trajectory == {
        "thought_0": "t",
        "tool_name_0": "ask_for_clarification",
    }


def test_the_answer_resumes_the_saved_step_without_restarting_the_loop(
    db, ctx, operation, monkeypatch, session_factory
):
    """The point of ResumableReAct: no replay, so the pre-pause LM calls are not repaid."""
    agent(monkeypatch, step(0, "ask_for_clarification", ASK))
    with pytest.raises(NeedsInput):
        run(ctx)

    answer(db, operation, "clarify:0", [{"option": "Schools"}])
    resumed: list = []
    started: list = []

    class Fake:
        def start(self, **inputs):
            started.append(1)
            raise AssertionError("a resumed loop must not start again")

        def resume(self, step, **inputs):
            resumed.append(step)
            return done()

    monkeypatch.setattr(concept_filters, "build_concept_filter_agent", lambda: Fake())

    assert run(StepContext(operation.id, session_factory))["filter_groups"] == 1
    assert started == []
    assert resumed[0].trajectory["observation_0"] == ["Schools"]


def test_an_unsatisfiable_query_fails_the_operation(ctx, monkeypatch):
    """A legitimate outcome, but the reason belongs in the error, not in a missing artifact."""
    agent(monkeypatch, step(0, "mark_unsatisfiable", {"reason": "no concept for it"}))

    with pytest.raises(concept_filters.UnsatisfiableQuery, match="no concept for it"):
        run(ctx)

    assert ctx.get_artifact(artifacts.CONCEPT_FILTERS) is None
