"""The two suggest-then-choose steps, from the model's output to the chosen artifact."""

import dspy
import pytest

from factories import make_operation, make_session, make_user
from research_mapper.engine.context import NeedsInput, StepContext
from research_mapper.engine.enums import DecisionType
from research_mapper.engine.models import Decision
from research_mapper.models.sparse_search import LuceneQuery
from research_mapper.workflows.evidence_map import artifacts
from research_mapper.workflows.evidence_map.steps import sparse_query

A = {"query": "hpv AND uptake"}
B = {"query": "hpv AND refusal"}


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


def test_regenerate_ignores_the_stored_suggestions(ctx, restart, monkeypatch):
    suggest_queries(monkeypatch, A)
    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(ctx, sparse_query.SparseQueryParams())

    calls = suggest_queries(monkeypatch, B)
    with pytest.raises(NeedsInput):
        sparse_query.EnhanceSparseQuery().run(
            restart(), sparse_query.SparseQueryParams(regenerate=True)
        )

    assert len(calls) == 1
    stored = restart().get_artifact(artifacts.SUGGESTED_SEARCH_QUERIES)
    assert stored is not None
    assert [query.model_dump(mode="json") for query in stored.queries] == [B]
