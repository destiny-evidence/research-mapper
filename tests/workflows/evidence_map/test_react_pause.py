"""Pins the dspy.ReAct behaviour the in-loop pause depends on.

Runs against DummyLM, so no network and no key. If a dspy upgrade changes any of
this, the failure lands here rather than as a fabricated answer in production.
"""

import threading

import dspy
import pytest
from dspy.utils.dummies import DummyLM

from research_mapper.engine.context import NeedsInput


class Answer(dspy.Signature):
    """Answer the question."""

    question: str = dspy.InputField()
    answer: str = dspy.OutputField()


def script() -> DummyLM:
    """An LM that calls the clarify tool, then finishes."""
    return DummyLM(
        [
            {
                "next_thought": "The scope is ambiguous.",
                "next_tool_name": "clarify",
                "next_tool_args": {"question": "global or regional?"},
            },
            {"next_thought": "Done.", "next_tool_name": "finish", "next_tool_args": {}},
            {"reasoning": "r", "answer": "FABRICATED"},
        ]
    )


def test_needs_input_escapes_react():
    """The whole in-loop pause rests on ReAct catching Exception, not BaseException."""

    def clarify(question: str) -> str:
        """Ask the human."""
        raise NeedsInput(question)

    with dspy.context(lm=script()), pytest.raises(NeedsInput):
        dspy.ReAct(Answer, tools=[clarify])(question="q")


def test_an_ordinary_exception_is_swallowed_into_the_next_prompt():
    """Why NeedsInput must not be an Exception: the traceback becomes an observation."""

    def clarify(question: str) -> str:
        """Ask the human."""
        raise RuntimeError(question)

    with dspy.context(lm=script()):
        prediction = dspy.ReAct(Answer, tools=[clarify])(question="q")

    assert prediction.answer == "FABRICATED", "the LM answered from the traceback"
    assert "Execution error in clarify" in prediction.trajectory["observation_0"]


def test_the_tool_returns_the_answer_on_replay():
    """Ask-and-restart: the next pass re-runs the tool, which now finds an answer."""
    answers = {"global or regional?": "regional"}
    calls: list[str] = []

    def clarify(question: str) -> str:
        """Ask the human."""
        calls.append(question)
        if question in answers:
            return answers[question]
        raise NeedsInput(question)

    with dspy.context(lm=script()):
        prediction = dspy.ReAct(Answer, tools=[clarify])(question="q")

    assert calls == ["global or regional?"], "asked once, answered from the record"
    assert prediction.trajectory["observation_0"] == "regional"


def test_pausing_inside_batch_discards_the_work_already_done():
    """Why a fan-out step must never ask: batch() propagates and drops finished results."""
    done: list[str] = []
    lock = threading.Lock()

    class Screen(dspy.Module):
        def forward(self, paper: str) -> dspy.Prediction:
            if paper == "paper-3":
                raise NeedsInput("is a preprint in scope?")
            with lock:
                done.append(paper)
            return dspy.Prediction(include="yes")

    papers = [dspy.Example(paper=f"paper-{i}").with_inputs("paper") for i in range(8)]
    with dspy.context(lm=DummyLM([{"include": "yes"}] * 20)):
        with pytest.raises(NeedsInput):
            Screen().batch(papers, num_threads=4)

    assert done, "papers were screened and their verdicts went with the exception"
