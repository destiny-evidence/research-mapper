import logging
from typing import Any

import dspy

from research_mapper.models.react import Step

logger = logging.getLogger(__name__)


class ResumableReAct(dspy.ReAct):
    """
    A `dspy.ReAct` agent driven one step at a time rather than run start to
    finish in one call: every iteration's proposed action is surfaced to the
    caller as a `Step` *before* it executes, and only runs once the caller
    calls `resume()` on it. `forward()` (and therefore calling the module
    directly) is a thin convenience wrapper — it does nothing `resume()`
    doesn't already do, it just keeps approving every step without pausing
    until the run finishes, for callers that don't want manual control.

    Deliberately reuses `dspy.ReAct`'s own trajectory machinery — `self.react`,
    `self.extract`, `self._call_with_potential_trajectory_truncation` — rather
    than reimplementing it. `_call_with_potential_trajectory_truncation` is a
    "private" method of the base class, so this is coupled to dspy's current
    implementation of `ReAct.forward` — worth re-checking on a dspy upgrade.
    """

    def forward(self, **input_args) -> dspy.Prediction:
        result = self.resume(None, **input_args)
        while isinstance(result, Step):
            result = self.resume(result, **input_args)
        return result

    def start(self, **input_args) -> Step | dspy.Prediction:
        """Equivalent to `resume(None, **input_args)` — begins a new run."""
        return self.resume(None, **input_args)

    def resume(self, step: Step | None, **input_args) -> Step | dspy.Prediction:
        """
        Advances a run by one iteration.
        :param step: the previously-surfaced `Step` to approve and continue from — its
            tool is executed here — or `None` to begin a new run
        :param input_args: the same inputs the run was/would be started with; must match
            across every call for a given run, same as `forward()`'s own arguments would
        :return: the agent's next proposed `Step`, or the final `Prediction` once the
            run finishes (the tool call proposed `finish`, or `max_iters` was reached)
        """
        max_iters = input_args.pop("max_iters", self.max_iters)
        trajectory = dict(step.trajectory) if step is not None else {}

        if step is not None:
            # A caller may have already supplied this step's observation (see
            # Step.with_observation) — e.g. a human's answer to a clarifying
            # question no tool could produce on its own. Only call the tool
            # for real if nothing's there yet.
            observation_key = f"observation_{step.idx}"
            if observation_key not in trajectory:
                trajectory[observation_key] = self._execute(step)
            if step.tool_name == "finish" or step.idx + 1 >= max_iters:
                return self._extract(trajectory, **input_args)

        idx = step.idx + 1 if step is not None else 0
        try:
            pred = self._call_with_potential_trajectory_truncation(
                self.react, trajectory, **input_args
            )
        except ValueError:
            logger.warning("Ending the trajectory: agent failed to select a valid tool")
            return self._extract(trajectory, **input_args)

        trajectory[f"thought_{idx}"] = pred.next_thought
        trajectory[f"tool_name_{idx}"] = pred.next_tool_name
        trajectory[f"tool_args_{idx}"] = pred.next_tool_args
        return Step(
            trajectory=trajectory,
            idx=idx,
            thought=pred.next_thought,
            tool_name=pred.next_tool_name,
            tool_args=pred.next_tool_args,
        )

    def _execute(self, step: Step) -> Any:
        try:
            return self.tools[step.tool_name](**step.tool_args)
        except Exception as exc:  # noqa: BLE001 - mirrors dspy.ReAct's own handling
            return f"Execution error in {step.tool_name}: {exc}"

    def _extract(self, trajectory: dict[str, Any], **input_args) -> dspy.Prediction:
        extract = self._call_with_potential_trajectory_truncation(
            self.extract, trajectory, **input_args
        )
        return dspy.Prediction(trajectory=trajectory, **extract)
