import dspy
import pytest
from dspy.utils.dummies import DummyLM

from research_mapper.workflows.evidence_map.fanout import ProgressTracker


class Recorder:
    """A StepContext stand-in that keeps every progress call, unthrottled."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int | None, int]] = []

    def progress(self, done, total=None, failed=0, note="") -> None:
        self.calls.append((done, total, failed))


class Screen(dspy.Module):
    def forward(self, paper: str) -> dspy.Prediction:
        if paper.startswith("bad"):
            raise RuntimeError("no abstract")
        return dspy.Prediction(include="yes")


def examples_for(papers: list[str]) -> list[dspy.Example]:
    return [dspy.Example(paper=p).with_inputs("paper") for p in papers]


def run(papers: list[str], ctx: Recorder, num_threads: int = 1) -> list:
    tracker = ProgressTracker(ctx, len(papers), note="screening")
    with dspy.context(lm=DummyLM([{"include": "yes"}] * 30)):
        return tracker.fan_out(Screen(), examples_for(papers), num_threads=num_threads)


def test_failed_items_come_back_as_none_in_order():
    ctx = Recorder()
    results = run(["ok-1", "bad-2", "ok-3"], ctx)

    assert [r is None for r in results] == [False, True, False]


def test_progress_counts_failures_as_they_happen():
    """Otherwise `failed` reads zero for the whole run and only corrects at the end."""
    ctx = Recorder()
    run(["bad-1", "ok-2"], ctx, num_threads=1)

    assert ctx.calls == [(1, 2, 1), (2, 2, 1)]


def test_every_item_is_reported_exactly_once():
    ctx = Recorder()
    papers = [f"ok-{i}" for i in range(20)] + [f"bad-{i}" for i in range(5)]
    run(papers, ctx, num_threads=4)

    assert len(ctx.calls) == 25
    assert max(done for done, _, _ in ctx.calls) == 25
    assert max(failed for _, _, failed in ctx.calls) == 5


def test_a_baseexception_escapes_rather_than_counting_as_a_failure():
    """NeedsInput aborts the fan-out; it is not one item going wrong."""

    class Asking(dspy.Module):
        def forward(self, paper: str) -> dspy.Prediction:
            raise KeyboardInterrupt

    ctx = Recorder()
    examples = [dspy.Example(paper="p").with_inputs("paper")]
    with (
        dspy.context(lm=DummyLM([{"include": "yes"}])),
        pytest.raises(KeyboardInterrupt),
    ):
        ProgressTracker(ctx, 1, note="screening").fan_out(
            Asking(), examples, num_threads=1
        )

    assert ctx.calls == []


def test_one_tracker_counts_across_several_fan_outs():
    """A paged step reports against the whole run, not restarting each page."""
    ctx = Recorder()
    tracker = ProgressTracker(ctx, total=4, note="screening")

    with dspy.context(lm=DummyLM([{"include": "yes"}] * 10)):
        tracker.fan_out(Screen(), examples_for(["ok-1", "ok-2"]), num_threads=1)
        tracker.fan_out(Screen(), examples_for(["ok-3", "ok-4"]), num_threads=1)

    assert ctx.calls == [(1, 4, 0), (2, 4, 0), (3, 4, 0), (4, 4, 0)]


def test_failures_carry_into_later_fan_outs():
    """Page two must not report failed=0 after page one lost an item."""
    ctx = Recorder()
    tracker = ProgressTracker(ctx, total=3, note="screening")

    with dspy.context(lm=DummyLM([{"include": "yes"}] * 10)):
        tracker.fan_out(Screen(), examples_for(["bad-1", "ok-2"]), num_threads=1)
        tracker.fan_out(Screen(), examples_for(["ok-3"]), num_threads=1)

    assert ctx.calls == [(1, 3, 1), (2, 3, 1), (3, 3, 1)]
    assert tracker.failed == 1


def test_a_resumed_step_starts_from_the_work_already_done():
    """`done` is the screened-reference count, so progress doesn't jump backwards."""
    ctx = Recorder()
    tracker = ProgressTracker(ctx, total=5, note="screening", done=3)
    tracker.start()

    with dspy.context(lm=DummyLM([{"include": "yes"}] * 10)):
        tracker.fan_out(Screen(), examples_for(["ok-4", "ok-5"]), num_threads=1)

    assert ctx.calls == [(3, 5, 0), (4, 5, 0), (5, 5, 0)]
