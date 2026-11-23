import logging
from itertools import groupby
from typing import Any

import dspy
from dspy.adapters.types.tool import (
    ToolCallResults,
    ToolCalls,
    _resolve_json_schema_reference,
)
from dspy.utils.exceptions import (
    AdapterParseError,
    ContextWindowExceededError,
    format_error_for_lm,
)

from research_mapper.models.react import Step

logger = logging.getLogger(__name__)

SUBMIT = "submit"
SUBMITTED = "Submitted."


class ResumableReAct(dspy.ReAct):
    """
    A `dspy.ReAct` agent driven one tool call at a time rather than run start to
    finish in one call: every proposed call is surfaced to the caller as a `Step`
    *before* it executes, and only runs once the caller calls `resume()` on it.
    `forward()` (and therefore calling the module directly) is a thin convenience
    wrapper that keeps approving every step without pausing until the run finishes.

    The model may propose several calls in one turn. They are queued: each is its own
    `Step`, in order, and the model takes its next turn only once all of them have
    run. The run ends when a `submit` call succeeds, with the signature's outputs.

    The run's state lives entirely in `Step.trajectory`, a plain dict keyed by call
    index so it can be persisted and resumed in another process: `thought_i`,
    `tool_name_i`, `tool_args_i`, `observation_i`, plus `turn_i` (the model turn the
    call came from; absent in trajectories saved before turns could hold several
    calls, where every call was its own turn) and `error_i` (set when the tool
    failed). The conversation history DSPy's ReAct predictor expects is rebuilt from
    it on every turn.

    Reuses `dspy.ReAct`'s tools, `submit` tool and predictor, plus two of its private
    helpers: `_turn_budget_inputs` and `_forced_submit`, and its schema resolver
    `_resolve_json_schema_reference`. Those, and the predictor's field names, are
    pinned by tests/test_react.py, so re-check them on a dspy upgrade.
    """

    def __init__(
        self,
        signature: type[dspy.Signature] | str,
        tools: list,
        max_iters: int = 20,
    ) -> None:
        super().__init__(signature, tools, max_iters=max_iters)
        # DSPy 3.5 builds `submit`'s arguments without inlining the `$defs` of a
        # structured output (it does for every other tool), so the model is sent a
        # `$ref` it can't follow and invents field names. Inline them like any tool.
        submit = self.tools["submit"]
        submit.args = {
            name: _resolve_json_schema_reference(schema)
            for name, schema in submit.args.items()
        }

    def forward(self, **input_args) -> dspy.Prediction:
        result = self.resume(None, **input_args)
        while isinstance(result, Step):
            result = self.resume(result, **input_args)
        return result

    def start(self, **input_args) -> Step | dspy.Prediction:
        """Equivalent to `resume(None, **input_args)` — begins a new run."""
        return self.resume(None, **input_args)

    def classify_step(self, step: Step) -> None:
        """
        A bare ResumableReAct has no domain-specific pause categories of its
        own, every Step it ever surfaces to a caller just means "call
        resume() again". Returning None unconditionally is a valid
        implementation of ResumableModule's `classify_step(...) -> T | None`
        for any T a wrapping module (e.g. TaxonomyConceptFilterGenerator)
        might use, it just never contributes an outcome of its own.
        """
        return None

    def resume(self, step: Step | None, **input_args) -> Step | dspy.Prediction:
        """
        Advances a run by one tool call.
        :param step: the previously-surfaced `Step` to approve and continue from — its
            tool is executed here — or `None` to begin a new run
        :param input_args: the same inputs the run was/would be started with; must match
            across every call for a given run, same as `forward()`'s own arguments would
        :return: the next proposed `Step` (queued from the same turn, or from the
            model's next turn), or the final `Prediction` once a `submit` succeeds or
            the turn budget runs out
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
                value, failed = self._execute(step)
                if step.tool_name == SUBMIT and not failed and isinstance(value, dict):
                    trajectory[observation_key] = SUBMITTED
                    return self._final(trajectory, value)
                trajectory[observation_key] = value
                if failed:
                    trajectory[f"error_{step.idx}"] = True
            queued = step.idx + 1
            if f"tool_name_{queued}" in trajectory:
                return self._step(trajectory, queued)

        turn = _next_turn(trajectory)
        history = self._history(trajectory, input_args, max_iters)
        if turn >= max_iters:
            return self._forced(trajectory, history, input_args, "max_iters", turn)

        turn_inputs = {
            **(self._inputs(input_args) if turn == 0 else {}),
            **self._turn_budget_inputs(turn, max_iters),
        }
        try:
            pred = self.react(
                history=history, tools=list(self.tools.values()), **turn_inputs
            )
            tool_calls = ToolCalls.model_validate(
                getattr(pred, "tool_calls", None) or {"tool_calls": []}
            )
        except AdapterParseError, ValueError:
            logger.warning(
                "Ending the trajectory: the agent's turn could not be parsed"
            )
            return self._forced(trajectory, history, input_args, "parse_error", turn)
        except ContextWindowExceededError:
            logger.warning("Ending the trajectory: the context window was exceeded")
            return self._forced(
                trajectory, history, input_args, "context_window_exceeded", turn
            )
        if not tool_calls.tool_calls:
            logger.warning("Ending the trajectory: the agent proposed no tool call")
            return self._forced(
                trajectory, history, input_args, "empty_tool_calls", turn
            )

        first = _call_count(trajectory)
        self._record(trajectory, turn, _text(pred.next_thought), tool_calls)
        return self._step(trajectory, first)

    def _execute(self, step: Step) -> tuple[Any, bool]:
        """Run the step's tool, returning its value and whether it failed."""
        tool = self.tools.get(step.tool_name)
        if tool is None:
            return f"Unknown tool: {step.tool_name}", True
        try:
            return tool(**step.tool_args), False
        except Exception as exc:  # noqa: BLE001 - mirrors dspy.ReAct's own handling
            detail = format_error_for_lm(exc, traceback_frames=5)
            return f"Execution error in {step.tool_name}: {detail}", True

    def _inputs(self, input_args: dict[str, Any]) -> dict[str, Any]:
        return {
            name: input_args[name]
            for name in self.signature.input_fields
            if name in input_args
        }

    def _record(
        self,
        trajectory: dict[str, Any],
        turn: int,
        thought: str,
        tool_calls: ToolCalls,
    ) -> None:
        """Append one model turn's calls to the trajectory, none executed yet."""
        first = _call_count(trajectory)
        for offset, call in enumerate(tool_calls.tool_calls):
            idx = first + offset
            trajectory[f"thought_{idx}"] = thought
            trajectory[f"tool_name_{idx}"] = call.name
            trajectory[f"tool_args_{idx}"] = call.args or {}
            trajectory[f"turn_{idx}"] = turn

    def _history(
        self, trajectory: dict[str, Any], input_args: dict[str, Any], max_iters: int
    ) -> dspy.History:
        """The conversation so far, one event per completed model turn, shaped as
        dspy.ReAct records it: the run's inputs on the first event only, that turn's
        budget, its thought, and its tool calls with their results."""
        events: list[dict[str, Any]] = []
        for turn, idxs in _turns(trajectory):
            event: dict[str, Any] = self._inputs(input_args) if not events else {}
            event.update(self._turn_budget_inputs(turn, max_iters))
            if thought := trajectory.get(f"thought_{idxs[0]}"):
                event["next_thought"] = thought
            # Ids are derived, not stored, so a rebuilt request matches the last one
            # exactly, which keeps provider prompt caching working.
            calls = [
                ToolCalls.ToolCall(
                    id=f"call_{turn}_{offset}",
                    name=trajectory[f"tool_name_{idx}"],
                    args=trajectory.get(f"tool_args_{idx}") or {},
                )
                for offset, idx in enumerate(idxs)
            ]
            executed = [
                (call, idx)
                for call, idx in zip(calls, idxs, strict=True)
                if f"observation_{idx}" in trajectory
            ]
            tool_calls = ToolCalls(tool_calls=calls)
            if executed:
                results = ToolCallResults.from_tool_calls_and_values(
                    [call for call, _ in executed],
                    [trajectory[f"observation_{idx}"] for _, idx in executed],
                    [bool(trajectory.get(f"error_{idx}")) for _, idx in executed],
                )
                tool_calls = tool_calls.model_copy(
                    update={"tool_call_results": results}
                )
            event["tool_calls"] = tool_calls
            events.append(event)
        return dspy.History(messages=events)

    def _forced(
        self,
        trajectory: dict[str, Any],
        history: dspy.History,
        input_args: dict[str, Any],
        reason: str,
        turn: int,
    ) -> dspy.Prediction:
        """Ask for a submit outright, as dspy.ReAct does when its loop ends early."""
        pending = self._inputs(input_args) if not history.messages else {}
        pred = self._forced_submit(history, pending, reason, turn)
        last = pred.history.messages[-1]
        submitted = ToolCalls(
            tool_calls=[
                call for call in last["tool_calls"].tool_calls if call.name == SUBMIT
            ][:1]
        )
        first = _call_count(trajectory)
        self._record(trajectory, turn, _text(last.get("next_thought")), submitted)
        trajectory[f"observation_{first}"] = SUBMITTED
        outputs = {name: pred[name] for name in self.signature.output_fields}
        return self._final(trajectory, outputs)

    def _final(
        self, trajectory: dict[str, Any], outputs: dict[str, Any]
    ) -> dspy.Prediction:
        thoughts = [
            trajectory.get(f"thought_{idxs[0]}") for _, idxs in _turns(trajectory)
        ]
        return dspy.Prediction(
            **outputs, trajectory=trajectory, reasoning=_numbered(thoughts)
        )

    def _step(self, trajectory: dict[str, Any], idx: int) -> Step:
        return Step(
            trajectory=trajectory,
            idx=idx,
            thought=trajectory.get(f"thought_{idx}") or "",
            tool_name=trajectory[f"tool_name_{idx}"],
            tool_args=trajectory.get(f"tool_args_{idx}") or {},
        )


def reasoning_from_history(history: dspy.History | None) -> str:
    """
    A plain dspy.ReAct run's thoughts, numbered in order. dspy.ReAct stopped
    returning a `reasoning` field in 3.5, so this rebuilds one from its history in
    the same format ResumableReAct uses.
    """
    messages = history.messages if history is not None else []
    return _numbered([_text(event.get("next_thought")) for event in messages])


def _numbered(thoughts: list[Any]) -> str:
    lines = [str(thought).strip() for thought in thoughts if thought]
    return "\n".join(f"{n}. {line}" for n, line in enumerate(lines, start=1) if line)


def _text(value: Any) -> str:
    """dspy.Reasoning and plain strings alike, as a string."""
    if value is None:
        return ""
    return getattr(value, "content", None) or str(value)


def _call_count(trajectory: dict[str, Any]) -> int:
    return sum(1 for key in trajectory if key.startswith("tool_name_"))


def _turn_of(trajectory: dict[str, Any], idx: int) -> int:
    # Before a turn could hold several calls, every call was its own turn.
    return trajectory.get(f"turn_{idx}", idx)


def _turns(trajectory: dict[str, Any]) -> list[tuple[int, list[int]]]:
    """Each model turn with its call indices, in order."""
    idxs = range(_call_count(trajectory))
    return [
        (turn, list(group))
        for turn, group in groupby(idxs, key=lambda idx: _turn_of(trajectory, idx))
    ]


def _next_turn(trajectory: dict[str, Any]) -> int:
    count = _call_count(trajectory)
    return _turn_of(trajectory, count - 1) + 1 if count else 0
