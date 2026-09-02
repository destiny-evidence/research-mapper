"""The two suggest-then-choose steps, from the model's output to the chosen artifact."""

import dspy
import pytest

from factories import make_operation, make_session, make_user
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision, ResearchSession, User
from research_mapper.models.screening import ScreeningCriterion
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.steps import screening, sparse_query

A = {"query": "hpv AND uptake"}
B = {"query": "hpv AND refusal"}
INCLUDE = {"criterion_type": "inclusion", "description": "peer reviewed"}
EXCLUDE = {"criterion_type": "exclusion", "description": "not english"}


@pytest.fixture
def operation(db):
    user = make_user(db)
    session = make_session(db, user)
    return make_operation(db, session, user, type="enhance_sparse_query")


@pytest.fixture
def ctx(operation, session_factory):
    return StepContext(operation.id, session_factory)


@pytest.fixture
def restart(operation, session_factory):
    """A fresh context on the same operation, as the worker builds on a resume."""
    return lambda: StepContext(operation.id, session_factory)


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


def suggest(monkeypatch, module, field, values) -> list:
    """Stand in for the LM, recording each time it is asked."""
    calls: list = []

    def fake_call(self, **kwargs):
        calls.append(kwargs)
        return dspy.Prediction(**{field: values}, reasoning="because")

    monkeypatch.setattr(module, "__call__", fake_call)
    return calls


def suggest_queries(monkeypatch, *queries) -> list:
    return suggest(
        monkeypatch,
        sparse_query.SparseQueryGenerator,
        "search_queries",
        [LuceneQuery(**q) for q in queries],
    )


def suggest_criteria(monkeypatch, *criteria) -> list:
    return suggest(
        monkeypatch,
        screening.CriteriaGenerator,
        "screening_criteria",
        [ScreeningCriterion(**c) for c in criteria],
    )


def test_suggested_queries_are_stored_before_the_user_is_asked(ctx, monkeypatch):
    """The artifact lands first, so a crash while waiting costs no LM call."""
    suggest_queries(monkeypatch, A, B)

    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(ctx, sparse_query.SparseQueryParams())

    stored = ctx.get_artifact(artifacts.SUGGESTED_SEARCH_QUERIES)
    assert stored == artifacts.SearchQueries.model_validate(
        {"queries": [A, B], "reasoning": "because"}
    )

    spec = ctx.pending_decisions["select_queries"]
    assert [option["value"] for option in spec.options] == [A, B]
    assert [option["label"] for option in spec.options] == [A["query"], B["query"]]


def test_only_the_chosen_queries_reach_the_chosen_artifact(
    db, ctx, operation, restart, monkeypatch
):
    calls = suggest_queries(monkeypatch, A, B)
    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(ctx, sparse_query.SparseQueryParams())

    answer(db, operation, "select_queries", [A])
    result = sparse_query.EnhanceSparseQuery().run(
        restart(), sparse_query.SparseQueryParams()
    )

    assert result == {"suggested": 2, "selected": 1, "version": 1}
    chosen = restart().get_artifact(artifacts.SEARCH_QUERIES)
    assert chosen is not None
    assert [query.model_dump(mode="json") for query in chosen.queries] == [A]
    assert len(calls) == 1, "the replay must not spend another LM call"


def test_regenerate_ignores_the_stored_suggestions(
    ctx, operation, db, session_factory, monkeypatch
):
    """Asking again is a new operation, and it starts from the model, not the store."""
    suggest_queries(monkeypatch, A)
    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(ctx, sparse_query.SparseQueryParams())

    calls = suggest_queries(monkeypatch, B)
    again = make_operation(
        db,
        db.get(ResearchSession, operation.research_session_id),
        db.get(User, operation.created_by_id),
        type="enhance_sparse_query",
        params={"regenerate": True},
    )
    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(
            StepContext(again.id, session_factory),
            sparse_query.SparseQueryParams(regenerate=True),
        )

    assert len(calls) == 1
    stored = ctx.get_artifact(artifacts.SUGGESTED_SEARCH_QUERIES)
    assert [query.model_dump(mode="json") for query in stored.queries] == [B]


def test_resuming_a_regenerate_keeps_what_the_user_was_shown(
    ctx, restart, monkeypatch, db, operation
):
    """The second run must not quietly replace the options that were answered."""
    suggest_queries(monkeypatch, A)
    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(
            ctx, sparse_query.SparseQueryParams(regenerate=True)
        )

    calls = suggest_queries(monkeypatch, B)
    answer(db, operation, "select_queries", [A])
    sparse_query.EnhanceSparseQuery().run(
        restart(), sparse_query.SparseQueryParams(regenerate=True)
    )

    assert calls == []
    stored = restart().get_artifact(artifacts.SUGGESTED_SEARCH_QUERIES)
    assert [query.model_dump(mode="json") for query in stored.queries] == [A]


def test_screening_criteria_are_suggested_then_narrowed(
    db, ctx, operation, restart, monkeypatch
):
    suggest_criteria(monkeypatch, INCLUDE, EXCLUDE)
    with pytest.raises(NeedsInput):
        screening.GenerateScreeningCriteria().run(
            ctx, screening.GenerateScreeningCriteriaParams()
        )

    spec = ctx.pending_decisions["select_criteria"]
    assert [option["value"] for option in spec.options] == [INCLUDE, EXCLUDE]
    assert spec.options[0]["label"] == "Inclusion - peer reviewed"

    answer(db, operation, "select_criteria", [EXCLUDE])
    result = screening.GenerateScreeningCriteria().run(
        restart(), screening.GenerateScreeningCriteriaParams()
    )

    assert result == {"suggested": 2, "selected": 1, "version": 1}
    chosen = restart().get_artifact(artifacts.SCREENING_CRITERIA)
    assert chosen is not None
    assert [c.model_dump(mode="json") for c in chosen.criteria] == [EXCLUDE]
