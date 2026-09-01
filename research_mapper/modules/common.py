from typing import runtime_checkable, Protocol, Any

import dspy

from research_mapper.models.react import Step


@runtime_checkable
class ResumableModule(Protocol):
    """
    Structural contract for a dspy.Module that can be driven step-by-step
    like ResumableReAct itself: Step in, Step-or-Prediction out; whether
    it's a raw ResumableReAct or a higher-level module that composes one
    internally (e.g. TaxonomyConceptFilterGenerator, which builds a fresh
    ResumableReAct per call and layers its own concerns on top). A Protocol
    rather than an ABC: dspy.Module uses its own metaclass (ProgramMeta),
    which conflicts with ABCMeta, so any shared base has to be structural,
    not nominal.
    """

    def start(self, **input_args: Any) -> Step | dspy.Prediction: ...
    def resume(
        self, step: Step | None, **input_args: Any
    ) -> Step | dspy.Prediction: ...
