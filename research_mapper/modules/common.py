import copy
from typing import Any, Protocol, runtime_checkable

import dspy

from research_mapper.models.react import Step


def plain_reasoning(prediction: dspy.Prediction) -> dspy.Prediction:
    """
    A ChainOfThought prediction with its `reasoning` as a plain str. Since DSPy 3.5
    it is a `dspy.Reasoning`, which pydantic `str` fields and JSON both reject, so
    modules convert it here rather than every caller doing so.

    With a model that reasons natively, DSPy fills `reasoning` from the provider's
    reasoning summary, which is None when the provider returns none. That becomes
    "", so callers can still store it.

    Returns a copy: the original is the object DSPy records in optimiser traces,
    which keep the `dspy.Reasoning` it actually produced. The copy keeps any other
    completions, and gets its own field store so the original is left untouched.
    """
    if "reasoning" not in prediction:
        return prediction
    reasoning = prediction.reasoning
    if isinstance(reasoning, str):
        return prediction
    plain = copy.copy(prediction)
    plain._store = dict(prediction._store)
    plain.reasoning = "" if reasoning is None else str(reasoning)
    return plain


@runtime_checkable
class ResumableModule[T](Protocol):
    """
    Structural contract for a dspy.Module that can be driven step-by-step
    like ResumableReAct itself: Step in, Step-or-Prediction out; whether
    it's a raw ResumableReAct or a higher-level module that composes one
    internally (e.g. TaxonomyConceptFilterGenerator, which builds a fresh
    ResumableReAct per call and layers its own concerns on top). A Protocol
    rather than an ABC: dspy.Module uses its own metaclass (ProgramMeta),
    which conflicts with ABCMeta, so any shared base has to be structural,
    not nominal.

    classify_step() is what makes a wrapping module genuinely reusable
    across callers: it's the one place that knows which of a module's own
    tools are meaningful pause points and what they mean, so every caller
    (a blocking TUI loop, a persist-and-suspend worker loop, or some future
    third caller) dispatches on the same pre-classified outcome instead of
    each re-deriving "what does this tool_name mean" from a Step's raw
    tool_name/tool_args itself, which would let different callers silently
    diverge on what the same module instance's steps mean. `T` is whatever
    union of outcome types a given module's classify_step actually returns
    (e.g. TaxonomyConceptFilterGenerator's is `str | ClarificationOptions`);
    `None` is the one outcome every conforming module agrees on universally:
    "not a pause point, just call resume() again".
    """

    def start(self, **input_args: Any) -> Step | dspy.Prediction: ...
    def resume(
        self, step: Step | None, **input_args: Any
    ) -> Step | dspy.Prediction: ...
    def classify_step(self, step: Step) -> T | None: ...
