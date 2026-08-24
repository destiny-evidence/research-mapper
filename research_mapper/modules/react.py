import logging
from collections.abc import Callable
from typing import Any

import dspy

from research_mapper.models.react import Suspended

logger = logging.getLogger(__name__)


class ResumableReAct(dspy.ReAct):
    """
    A `dspy.ReAct` agent that can pause instead of executing specific tools,
    handing control back to the caller with everything needed to resume
    later, rather than blocking until a human answers.

    Deliberately reuses `dspy.ReAct`'s own trajectory machinery — `self.react`,
    `self.extract`, `self._call_with_potential_trajectory_truncation` — rather
    than reimplementing it; only the iteration loop itself is overridden, to
    add the suspend check. `_call_with_potential_trajectory_truncation` is a
    "private" method of the base class, so this is coupled to dspy's current
    implementation of `ReAct.forward` — worth re-checking on a dspy upgrade.
    """

    def __init__(
        self,
        signature: Any,
        tools: list[Callable],
        *,
        suspend_on: set[str],
        max_iters: int = 10,
    ) -> None:
        super().__init__(signature=signature, tools=tools, max_iters=max_iters)
        unknown = suspend_on - set(self.tools)
        if unknown:
            msg = f"suspend_on names tool(s) not present in tools: {sorted(unknown)}"
            raise ValueError(msg)
        self.suspend_on = suspend_on

    def forward(self, **input_args) -> dspy.Prediction | Suspended:
        return self._run(trajectory={}, start_idx=0, **input_args)

    def resume(
        self, trajectory: dict[str, Any], idx: int, observation: Any, **input_args
    ) -> dspy.Prediction | Suspended:
        """
        Continues a previously suspended run.
        :param trajectory: the trajectory `Suspended` returned when this run paused
        :param idx: the iteration `Suspended` paused at
        :param observation: the answer obtained for the tool call that paused the run —
            spliced in as if the suspended tool had returned it itself
        :param input_args: the same input arguments the original `forward()` call used
        :return: a `dspy.Prediction` if the run now finishes, or another `Suspended`
            if it pauses again
        """
        trajectory = dict(trajectory)
        trajectory[f"observation_{idx}"] = observation
        return self._run(trajectory=trajectory, start_idx=idx + 1, **input_args)

    def _run(
        self, trajectory: dict[str, Any], start_idx: int, **input_args
    ) -> dspy.Prediction | Suspended:
        max_iters = input_args.pop("max_iters", self.max_iters)
        for idx in range(start_idx, max_iters):
            try:
                pred = self._call_with_potential_trajectory_truncation(
                    self.react, trajectory, **input_args
                )
            except ValueError:
                logger.warning(
                    "Ending the trajectory: agent failed to select a valid tool"
                )
                break

            trajectory[f"thought_{idx}"] = pred.next_thought
            trajectory[f"tool_name_{idx}"] = pred.next_tool_name
            trajectory[f"tool_args_{idx}"] = pred.next_tool_args

            if pred.next_tool_name in self.suspend_on:
                return Suspended(
                    trajectory=trajectory,
                    idx=idx,
                    tool_name=pred.next_tool_name,
                    tool_args=pred.next_tool_args,
                )

            try:
                trajectory[f"observation_{idx}"] = self.tools[pred.next_tool_name](
                    **pred.next_tool_args
                )
            except Exception as exc:  # noqa: BLE001 - mirrors dspy.ReAct's own handling
                trajectory[f"observation_{idx}"] = (
                    f"Execution error in {pred.next_tool_name}: {exc}"
                )

            if pred.next_tool_name == "finish":
                break

        extract = self._call_with_potential_trajectory_truncation(
            self.extract, trajectory, **input_args
        )
        return dspy.Prediction(trajectory=trajectory, **extract)
