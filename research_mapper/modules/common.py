from typing import Any, Protocol, runtime_checkable

import dspy

from research_mapper.models.react import Step


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
